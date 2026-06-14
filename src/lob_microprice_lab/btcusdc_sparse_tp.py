from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SparseTakeProfitPolicy:
    take_profit_bps: float
    horizon_minutes: int
    taker_roundtrip_fee_bps: float = 8.0


SPARSE_ENTRY_COLUMNS = [
    "fold",
    "signal_idx",
    "idx",
    "entry_delay_min",
    "signal_timestamp",
    "timestamp",
    "replay_date",
    "signal",
    "entry_px",
    "threshold",
    "lookback_minutes",
    "horizon_minutes",
    "direction",
    "filter_feature",
    "quantile",
]


def annotate_sparse_tp_delay_outcomes(
    ledgers_by_delay: Mapping[int, pd.DataFrame],
    *,
    quote_surcharge_bps: float = 0.5,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for delay, ledger in sorted(ledgers_by_delay.items(), key=lambda item: int(item[0])):
        if ledger.empty:
            continue
        for _, row in ledger.iterrows():
            signal = int(row["signal"])
            entry_px = float(row["entry_px"])
            tp_bps = float(row.get("tp_bps", 0.0))
            net_pnl_bps = float(row["net_pnl_bps"])
            exit_reason = str(row.get("exit_reason", ""))
            out = row.to_dict()
            out.update(
                {
                    "entry_delay_min": int(delay),
                    "tp_target_px": float(entry_px * (1.0 + signal * tp_bps / 10000.0)),
                    "tp_hit": bool(exit_reason == "take_profit"),
                    "final_net_pnl_bps": float(net_pnl_bps - float(quote_surcharge_bps)),
                    "is_loss_after_surcharge": bool(net_pnl_bps - float(quote_surcharge_bps) <= 0.0),
                }
            )
            rows.append(out)
    return pd.DataFrame(rows)


def shift_sparse_entries_to_delay(
    entries: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    folds: Iterable[tuple[int, str, str, str, str]],
    entry_delay_minutes: int,
    bars_prepared: bool = False,
) -> pd.DataFrame:
    if entries.empty:
        return entries.copy()

    if bars_prepared:
        ordered_bars = bars
    else:
        ordered_bars = bars.copy().sort_values("timestamp").reset_index(drop=True)
        ordered_bars["timestamp"] = pd.to_datetime(ordered_bars["timestamp"], utc=True)
        ordered_bars["open"] = pd.to_numeric(ordered_bars["open"], errors="coerce")
    fold_windows = {
        int(fold): (pd.Timestamp(validation_start, tz="UTC"), pd.Timestamp(validation_end, tz="UTC"))
        for fold, _, _, validation_start, validation_end in folds
    }

    rows: list[dict[str, object]] = []
    max_idx = len(ordered_bars) - 1
    for _, row in entries.iterrows():
        fold = int(row["fold"])
        if fold not in fold_windows:
            continue
        entry_idx = int(row["signal_idx"]) + int(entry_delay_minutes)
        if entry_idx > max_idx:
            continue
        entry_ts = pd.Timestamp(ordered_bars.loc[entry_idx, "timestamp"])
        validation_start, validation_end = fold_windows[fold]
        if not (entry_ts >= validation_start and entry_ts < validation_end):
            continue
        out = row.to_dict()
        out.update(
            {
                "idx": int(entry_idx),
                "entry_delay_min": int(entry_delay_minutes),
                "timestamp": entry_ts,
                "replay_date": str(entry_ts.date()),
                "entry_px": float(ordered_bars.loc[entry_idx, "open"]),
            }
        )
        rows.append(out)
    return pd.DataFrame(rows, columns=list(entries.columns))


def summarize_boolean_runs(scan: pd.DataFrame, *, value_col: str, index_col: str) -> pd.DataFrame:
    if scan.empty:
        return pd.DataFrame(columns=["value", "start", "end", "count"])

    ordered = scan[[index_col, value_col]].copy().sort_values(index_col).reset_index(drop=True)
    rows: list[dict[str, object]] = []
    current_value = bool(ordered.loc[0, value_col])
    start = int(ordered.loc[0, index_col])
    previous = start
    count = 1
    for _, row in ordered.iloc[1:].iterrows():
        idx = int(row[index_col])
        value = bool(row[value_col])
        if value == current_value and idx == previous + 1:
            previous = idx
            count += 1
            continue
        rows.append({"value": current_value, "start": int(start), "end": int(previous), "count": int(count)})
        current_value = value
        start = idx
        previous = idx
        count = 1
    rows.append({"value": current_value, "start": int(start), "end": int(previous), "count": int(count)})
    return pd.DataFrame(rows, columns=["value", "start", "end", "count"])


def _format_index_ranges(values: list[int]) -> str:
    if not values:
        return ""
    ordered = sorted(set(int(v) for v in values))
    ranges: list[str] = []
    start = ordered[0]
    prev = ordered[0]
    for value in ordered[1:]:
        if value == prev + 1:
            prev = value
            continue
        ranges.append(str(start) if start == prev else f"{start}-{prev}")
        start = value
        prev = value
    ranges.append(str(start) if start == prev else f"{start}-{prev}")
    return ",".join(ranges)


def summarize_sparse_delay_signal_fragility(
    combined_tp_ledger: pd.DataFrame,
    *,
    quote_surcharge_bps: float = 0.5,
) -> pd.DataFrame:
    if combined_tp_ledger.empty:
        return pd.DataFrame(
            columns=[
                "fold",
                "signal_idx",
                "signal_timestamp",
                "signal",
                "delay_count",
                "loss_delay_count",
                "loss_delay_ranges",
                "take_profit_delay_count",
                "worst_delay",
                "worst_final_net_pnl_bps",
                "best_final_net_pnl_bps",
                "mean_final_net_pnl_bps",
            ]
        )

    ledger = combined_tp_ledger.copy()
    ledger["scan_entry_delay_min"] = pd.to_numeric(ledger["scan_entry_delay_min"], errors="coerce").astype(int)
    ledger["final_net_pnl_bps"] = pd.to_numeric(ledger["net_pnl_bps"], errors="coerce").fillna(0.0) - float(quote_surcharge_bps)
    ledger["signal_timestamp"] = pd.to_datetime(ledger["signal_timestamp"], utc=True)
    ledger["is_loss_after_surcharge"] = ledger["final_net_pnl_bps"] <= 0.0
    ledger["tp_hit"] = ledger["exit_reason"].astype(str) == "take_profit"

    rows: list[dict[str, object]] = []
    key_cols = ["fold", "signal_idx", "signal_timestamp", "signal"]
    for key, grp in ledger.groupby(key_cols, sort=True):
        fold, signal_idx, signal_ts, signal = key
        final_net = pd.to_numeric(grp["final_net_pnl_bps"], errors="coerce").fillna(0.0)
        worst_pos = final_net.idxmin()
        loss_delays = grp.loc[grp["is_loss_after_surcharge"], "scan_entry_delay_min"].astype(int).tolist()
        rows.append(
            {
                "fold": int(fold),
                "signal_idx": int(signal_idx),
                "signal_timestamp": signal_ts,
                "signal": int(signal),
                "delay_count": int(grp["scan_entry_delay_min"].nunique()),
                "loss_delay_count": int(len(loss_delays)),
                "loss_delay_ranges": _format_index_ranges(loss_delays),
                "take_profit_delay_count": int(grp["tp_hit"].sum()),
                "worst_delay": int(ledger.loc[worst_pos, "scan_entry_delay_min"]),
                "worst_final_net_pnl_bps": float(final_net.loc[worst_pos]),
                "best_final_net_pnl_bps": float(final_net.max()),
                "mean_final_net_pnl_bps": float(final_net.mean()),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["loss_delay_count", "worst_final_net_pnl_bps", "fold", "signal_idx"],
        ascending=[False, True, True, True],
    ).reset_index(drop=True)


def summarize_sparse_delay_scan(
    scan: pd.DataFrame,
    *,
    pass_col: str,
    total_col: str,
    min_trade_col: str,
) -> dict[str, object]:
    if scan.empty:
        return {
            "delay_count": 0,
            "pass_count": 0,
            "fail_count": 0,
            "pass_rate": 0.0,
            "fail_delay_ranges": "",
            "worst_delay": None,
            "min_total_net_pnl_bps": 0.0,
            "mean_total_net_pnl_bps": 0.0,
            "min_trade_net_pnl_bps": 0.0,
        }

    ordered = scan.copy().sort_values("entry_delay_min").reset_index(drop=True)
    passed = ordered[pass_col].astype(bool)
    totals = pd.to_numeric(ordered[total_col], errors="coerce").fillna(0.0)
    min_trades = pd.to_numeric(ordered[min_trade_col], errors="coerce").fillna(0.0)
    fail_delays = ordered.loc[~passed, "entry_delay_min"].astype(int).tolist()
    worst_idx = totals.idxmin()
    return {
        "delay_count": int(len(ordered)),
        "pass_count": int(passed.sum()),
        "fail_count": int((~passed).sum()),
        "pass_rate": float(passed.mean()) if len(passed) else 0.0,
        "fail_delay_ranges": _format_index_ranges(fail_delays),
        "worst_delay": int(ordered.loc[worst_idx, "entry_delay_min"]),
        "min_total_net_pnl_bps": float(totals.min()),
        "mean_total_net_pnl_bps": float(totals.mean()),
        "min_trade_net_pnl_bps": float(min_trades.min()),
    }


def decide_sparse_tp_promotion(
    *,
    true_replay_gate_passed: bool,
    v60_holdout_dense_pass_count: int,
    v60_holdout_dense_delay_count: int,
    design_robust_holdout_pass_count: int,
    design_robust_holdout_delay_count: int,
) -> dict[str, object]:
    reasons: list[str] = []
    if not bool(true_replay_gate_passed):
        reasons.append("true_btcusdc_replay_failed")
    if int(v60_holdout_dense_pass_count) < int(v60_holdout_dense_delay_count):
        reasons.append("v60_dense_holdout_not_fully_robust")
    if int(design_robust_holdout_pass_count) < int(design_robust_holdout_delay_count):
        reasons.append("design_robust_selector_failed_holdout")
    promote = not reasons
    return {
        "promote_sparse_tp": bool(promote),
        "status": "promote" if promote else "reject",
        "primary_reasons": reasons,
    }


def summarize_sparse_tp_price_path(
    bars: pd.DataFrame,
    *,
    entry_idx: int,
    horizon_minutes: int,
    signal: int,
    entry_px: float,
    take_profit_bps: float,
) -> dict[str, object]:
    ordered_bars = bars.copy().reset_index(drop=True)
    ordered_bars["timestamp"] = pd.to_datetime(ordered_bars["timestamp"], utc=True)
    for col in ["open", "high", "low"]:
        ordered_bars[col] = pd.to_numeric(ordered_bars[col], errors="coerce")

    start_idx = int(entry_idx)
    max_idx = len(ordered_bars) - 1
    horizon_idx = min(start_idx + int(horizon_minutes), max_idx)
    path_start_idx = min(start_idx + 1, horizon_idx)
    path = ordered_bars.iloc[path_start_idx : horizon_idx + 1]
    side = int(signal)
    entry = float(entry_px)
    target_px = float(entry * (1.0 + side * float(take_profit_bps) / 10000.0))

    if path.empty:
        best_touch_idx = start_idx
        best_touch_px = entry
    elif side == 1:
        best_touch_idx = int(path["high"].idxmax())
        best_touch_px = float(ordered_bars.loc[best_touch_idx, "high"])
    else:
        best_touch_idx = int(path["low"].idxmin())
        best_touch_px = float(ordered_bars.loc[best_touch_idx, "low"])

    if side == 1:
        target_hit = bool(best_touch_px >= target_px)
        target_miss_bps = float((target_px / best_touch_px - 1.0) * 10000.0)
        hit_mask = path["high"] >= target_px if not path.empty else pd.Series(dtype=bool)
    else:
        target_hit = bool(best_touch_px <= target_px)
        target_miss_bps = float((best_touch_px / target_px - 1.0) * 10000.0)
        hit_mask = path["low"] <= target_px if not path.empty else pd.Series(dtype=bool)

    if bool(hit_mask.any()):
        first_hit_idx = int(hit_mask[hit_mask].index[0])
        first_hit_px = float(ordered_bars.loc[first_hit_idx, "high" if side == 1 else "low"])
        first_hit_timestamp = ordered_bars.loc[first_hit_idx, "timestamp"]
    else:
        first_hit_idx = None
        first_hit_px = float("nan")
        first_hit_timestamp = pd.NaT

    horizon_exit_px = float(ordered_bars.loc[horizon_idx, "open"])
    horizon_gross_pnl_bps = float((horizon_exit_px / entry - 1.0) * 10000.0 * side)
    return {
        "entry_idx": start_idx,
        "horizon_idx": int(horizon_idx),
        "path_start_idx": int(path_start_idx),
        "best_touch_idx": int(best_touch_idx),
        "best_touch_timestamp": ordered_bars.loc[best_touch_idx, "timestamp"],
        "best_touch_px": float(best_touch_px),
        "tp_target_px": float(target_px),
        "target_hit": bool(target_hit),
        "first_hit_idx": first_hit_idx,
        "first_hit_timestamp": first_hit_timestamp,
        "first_hit_px": float(first_hit_px),
        "target_miss_bps": float(target_miss_bps),
        "horizon_exit_px": float(horizon_exit_px),
        "horizon_gross_pnl_bps": float(horizon_gross_pnl_bps),
    }


def build_sparse_abs_return_entries(
    bars: pd.DataFrame,
    *,
    folds: Iterable[tuple[int, str, str, str, str]],
    entry_delay_minutes: int,
    lookback_minutes: int = 1440,
    horizon_minutes: int = 1440,
    quantile: float = 0.995,
    direction: str = "reversal",
) -> pd.DataFrame:
    from .btcusdc_independent_validation import _candidate_frame, _candidate_signals, _non_overlapping_indices

    ordered_bars = bars.copy().sort_values("timestamp").reset_index(drop=True)
    ordered_bars["timestamp"] = pd.to_datetime(ordered_bars["timestamp"], utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        if col in ordered_bars.columns:
            ordered_bars[col] = pd.to_numeric(ordered_bars[col], errors="coerce")

    frame = _candidate_frame(ordered_bars, int(lookback_minutes), int(horizon_minutes))
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    feature = pd.to_numeric(frame["abs_return_bps"], errors="coerce")
    direction_mode = str(direction)
    signals = _candidate_signals(frame, direction_mode).astype(int)
    valid_future = pd.to_numeric(frame["future_return_bps"], errors="coerce").notna()

    rows: list[dict[str, object]] = []
    for fold, cal_start, cal_end, validation_start, validation_end in folds:
        calibration_mask = (frame["timestamp"] >= pd.Timestamp(cal_start, tz="UTC")) & (frame["timestamp"] < pd.Timestamp(cal_end, tz="UTC"))
        calibration_feature = feature.loc[calibration_mask].dropna()
        if calibration_feature.empty:
            continue
        threshold = float(calibration_feature.quantile(float(quantile)))
        validation_mask = (frame["timestamp"] >= pd.Timestamp(validation_start, tz="UTC")) & (frame["timestamp"] < pd.Timestamp(validation_end, tz="UTC"))
        eligible = (feature >= threshold) & (signals != 0) & valid_future & validation_mask
        for idx in _non_overlapping_indices(eligible, horizon=int(horizon_minutes)):
            entry_idx = int(idx) + int(entry_delay_minutes)
            if entry_idx >= len(ordered_bars):
                continue
            entry_ts = pd.Timestamp(ordered_bars.loc[entry_idx, "timestamp"])
            if not (entry_ts >= pd.Timestamp(validation_start, tz="UTC") and entry_ts < pd.Timestamp(validation_end, tz="UTC")):
                continue
            rows.append(
                {
                    "fold": int(fold),
                    "signal_idx": int(idx),
                    "idx": int(entry_idx),
                    "entry_delay_min": int(entry_delay_minutes),
                    "signal_timestamp": frame.loc[idx, "timestamp"],
                    "timestamp": entry_ts,
                    "replay_date": str(entry_ts.date()),
                    "signal": int(signals.iloc[idx]),
                    "entry_px": float(ordered_bars.loc[entry_idx, "open"]),
                    "threshold": float(threshold),
                    "lookback_minutes": int(lookback_minutes),
                    "horizon_minutes": int(horizon_minutes),
                    "direction": direction_mode,
                    "filter_feature": "abs_return_bps",
                    "quantile": float(quantile),
                }
            )
    return pd.DataFrame(rows, columns=SPARSE_ENTRY_COLUMNS)


def summarize_sparse_tp_outcomes(tp_ledger: pd.DataFrame, *, quote_surcharge_bps: float = 0.5) -> dict[str, object]:
    if tp_ledger.empty:
        return {
            "trades": 0,
            "wins": 0,
            "win_rate": 0.0,
            "take_profit_rate": 0.0,
            "total_net_pnl_bps": 0.0,
            "mean_net_pnl_bps": 0.0,
            "min_trade_net_pnl_bps": 0.0,
            "max_trade_net_pnl_bps": 0.0,
            "max_hold_sec": 0.0,
        }
    final_net = pd.to_numeric(tp_ledger["net_pnl_bps"], errors="coerce").fillna(0.0) - float(quote_surcharge_bps)
    exit_reason = tp_ledger.get("exit_reason", pd.Series("", index=tp_ledger.index)).astype(str)
    hold_sec = pd.to_numeric(tp_ledger.get("hold_sec", pd.Series(0.0, index=tp_ledger.index)), errors="coerce").fillna(0.0)
    return {
        "trades": int(len(final_net)),
        "wins": int((final_net > 0).sum()),
        "win_rate": float((final_net > 0).mean()),
        "take_profit_rate": float((exit_reason == "take_profit").mean()),
        "total_net_pnl_bps": float(final_net.sum()),
        "mean_net_pnl_bps": float(final_net.mean()),
        "min_trade_net_pnl_bps": float(final_net.min()),
        "max_trade_net_pnl_bps": float(final_net.max()),
        "max_hold_sec": float(hold_sec.max()),
    }


def summarize_sparse_tp_by_fold_sets(
    tp_ledger: pd.DataFrame,
    *,
    design_folds: set[int],
    holdout_folds: set[int],
    quote_surcharge_bps: float = 0.5,
) -> dict[str, object]:
    folds = pd.to_numeric(tp_ledger.get("fold", pd.Series(dtype=int)), errors="coerce").fillna(-1).astype(int)
    out: dict[str, object] = {}
    for prefix, fold_set in (("design", set(int(x) for x in design_folds)), ("holdout", set(int(x) for x in holdout_folds))):
        mask = folds.isin(fold_set)
        summary = summarize_sparse_tp_outcomes(tp_ledger.loc[mask].copy(), quote_surcharge_bps=quote_surcharge_bps)
        for key, value in summary.items():
            out[f"{prefix}_{key}"] = value
    return out


def sparse_tp_to_contract_source_ledger(tp_ledger: pd.DataFrame) -> pd.DataFrame:
    source = pd.DataFrame(
        {
            "timestamp": tp_ledger["timestamp"],
            "best_bid": tp_ledger["entry_px"],
            "best_ask": tp_ledger["entry_px"],
            "signal": tp_ledger["signal"].astype(int),
            "fold": tp_ledger["fold"].astype(int),
            "raw_selective_signal": tp_ledger["signal"].astype(int),
            "traded": 1,
            "entry_px_taker": tp_ledger["entry_px"],
            "exit_px_taker": tp_ledger["exit_px"],
            "latency_sec": pd.to_numeric(tp_ledger.get("entry_delay_min", 1), errors="coerce").fillna(1.0).astype(float) * 60.0,
            "gross_pnl_bps": tp_ledger["gross_pnl_bps"],
            "cost_bps": tp_ledger["cost_bps"],
            "net_pnl_bps": tp_ledger["net_pnl_bps"],
            "exit_reason": tp_ledger["exit_reason"],
            "hold_sec": tp_ledger["hold_sec"],
            "take_profit_bps": tp_ledger["tp_bps"],
            "stop_loss_bps": 0.0,
            "reserve_horizon": True,
            "replay_date": tp_ledger["replay_date"],
            "threshold": tp_ledger["threshold"],
            "lookback_minutes": tp_ledger["lookback_minutes"],
            "horizon_minutes": tp_ledger["horizon_minutes"],
            "filter_feature": tp_ledger["filter_feature"],
            "quantile": tp_ledger["quantile"],
        }
    )
    source["equity_bps"] = pd.to_numeric(source["net_pnl_bps"], errors="coerce").fillna(0.0).cumsum()
    return source


def build_direction_flip_entries(entries: pd.DataFrame) -> pd.DataFrame:
    out = entries.copy()
    out["signal"] = -pd.to_numeric(out["signal"], errors="coerce").astype(int)
    if "direction" in out.columns:
        out["direction"] = out["direction"].astype(str) + "_direction_flip"
    return out


def sample_null_sparse_entries(
    entries: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    folds: Iterable[tuple[int, str, str, str, str]],
    seed: int,
    run_id: int,
) -> pd.DataFrame:
    ordered_bars = bars.copy().sort_values("timestamp").reset_index(drop=True)
    ordered_bars["timestamp"] = pd.to_datetime(ordered_bars["timestamp"], utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        if col in ordered_bars.columns:
            ordered_bars[col] = pd.to_numeric(ordered_bars[col], errors="coerce")

    rng = np.random.default_rng(int(seed))
    fold_windows = {int(fold): (pd.Timestamp(validation_start, tz="UTC"), pd.Timestamp(validation_end, tz="UTC")) for fold, _, _, validation_start, validation_end in folds}
    rows: list[dict[str, object]] = []
    for fold, group in entries.groupby("fold", sort=True):
        fold_int = int(fold)
        if fold_int not in fold_windows:
            continue
        val_start, val_end = fold_windows[fold_int]
        horizon = int(pd.to_numeric(group.get("horizon_minutes", pd.Series([1440])), errors="coerce").dropna().iloc[0])
        mask = (ordered_bars["timestamp"] >= val_start) & (ordered_bars["timestamp"] < val_end)
        idx_values = np.flatnonzero(mask.to_numpy(bool))
        idx_values = idx_values[idx_values + horizon < len(ordered_bars)]
        if len(idx_values) < len(group):
            raise ValueError(f"not enough null candidates for fold {fold_int}: need {len(group)}, found {len(idx_values)}")
        sampled_list: list[int] = []
        idx_set = set(int(x) for x in idx_values)
        min_idx = int(idx_values[0])
        max_idx = int(idx_values[-1])
        for _ in range(1000):
            sampled_list = []
            for _candidate_attempt in range(10000):
                candidate_int = int(rng.integers(min_idx, max_idx + 1))
                if candidate_int not in idx_set:
                    continue
                if all(abs(candidate_int - kept) >= horizon for kept in sampled_list):
                    sampled_list.append(candidate_int)
                    if len(sampled_list) == len(group):
                        break
            if len(sampled_list) == len(group):
                break
        if len(sampled_list) < len(group):
            raise ValueError(f"could not sample non-overlapping null candidates for fold {fold_int}")
        sampled = np.asarray(sorted(sampled_list), dtype=int)
        template = group.reset_index(drop=True)
        for row_number, bar_idx in enumerate(sampled):
            template_row = template.iloc[row_number].to_dict()
            entry_ts = pd.Timestamp(ordered_bars.loc[int(bar_idx), "timestamp"])
            template_row.update(
                {
                    "fold": fold_int,
                    "signal_idx": int(bar_idx) - int(template_row.get("entry_delay_min", 1)),
                    "idx": int(bar_idx),
                    "signal_timestamp": entry_ts - pd.Timedelta(minutes=int(template_row.get("entry_delay_min", 1))),
                    "timestamp": entry_ts,
                    "replay_date": str(entry_ts.date()),
                    "entry_px": float(ordered_bars.loc[int(bar_idx), "open"]),
                    "direction": "random_time_null",
                    "null_run": int(run_id),
                }
            )
            rows.append(template_row)
    return pd.DataFrame(rows)


def apply_take_profit_exit(entries: pd.DataFrame, bars: pd.DataFrame, policy: SparseTakeProfitPolicy, *, bars_prepared: bool = False) -> pd.DataFrame:
    """Apply a deterministic take-profit exit to sparse BTCUSDC entries.

    The returned ``net_pnl_bps`` is before the BTCUSDC quote surcharge. The
    existing V26 contract gate subtracts that surcharge in one place.
    """
    if entries.empty:
        return pd.DataFrame()
    if bars_prepared:
        ordered_bars = bars
    else:
        ordered_bars = bars.copy().reset_index(drop=True)
        ordered_bars["timestamp"] = pd.to_datetime(ordered_bars["timestamp"], utc=True)
        for col in ["open", "high", "low"]:
            ordered_bars[col] = pd.to_numeric(ordered_bars[col], errors="coerce")
    timestamp_values = pd.to_datetime(ordered_bars["timestamp"], utc=True).reset_index(drop=True)
    open_values = ordered_bars["open"].to_numpy(dtype=float)
    high_values = ordered_bars["high"].to_numpy(dtype=float)
    low_values = ordered_bars["low"].to_numpy(dtype=float)

    rows: list[dict[str, object]] = []
    max_idx = len(open_values) - 1
    for _, row in entries.iterrows():
        entry_idx = int(row["idx"])
        signal = int(row["signal"])
        entry_px = float(row["entry_px"])
        horizon_idx = min(entry_idx + int(policy.horizon_minutes), max_idx)
        exit_idx = horizon_idx
        exit_px = float(open_values[horizon_idx])
        exit_reason = "horizon"
        gross_pnl_bps = (exit_px / entry_px - 1.0) * 10000.0 * signal
        tp_px = entry_px * (1.0 + signal * float(policy.take_profit_bps) / 10000.0)

        for idx in range(entry_idx + 1, horizon_idx + 1):
            high = float(high_values[idx])
            low = float(low_values[idx])
            hit = high >= tp_px if signal == 1 else low <= tp_px
            if hit:
                exit_idx = idx
                exit_px = tp_px
                exit_reason = "take_profit"
                gross_pnl_bps = float(policy.take_profit_bps)
                break

        out = row.to_dict()
        out.update(
            {
                "tp_bps": float(policy.take_profit_bps),
                "exit_idx": int(exit_idx),
                "exit_timestamp": timestamp_values.iloc[exit_idx],
                "exit_px": float(exit_px),
                "exit_reason": exit_reason,
                "gross_pnl_bps": float(gross_pnl_bps),
                "cost_bps": float(policy.taker_roundtrip_fee_bps),
                "net_pnl_bps": float(gross_pnl_bps) - float(policy.taker_roundtrip_fee_bps),
                "hold_sec": float((timestamp_values.iloc[exit_idx] - pd.Timestamp(row["timestamp"])).total_seconds()),
            }
        )
        rows.append(out)
    return pd.DataFrame(rows)
