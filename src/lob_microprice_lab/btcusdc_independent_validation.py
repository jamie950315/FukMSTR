from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .btc_contract_data import parse_binance_public_zip


@dataclass(frozen=True)
class BTCUSDCCandidate:
    lookback_minutes: int
    horizon_minutes: int
    direction: str
    filter_feature: str
    threshold: float
    fee_bps: float = 8.5
    quantile: float | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_btcusdc_klines(kline_paths: Iterable[str | Path]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path_value in kline_paths:
        path = Path(path_value)
        if path.suffix.lower() == ".zip":
            df = parse_binance_public_zip(path, data_type="klines", interval=_infer_interval(path))
        else:
            df = pd.read_csv(path)
        missing = {"timestamp", "open", "high", "low", "close", "volume"}.difference(df.columns)
        if missing:
            raise ValueError(f"kline file missing columns: {sorted(missing)}")
        frame = df.copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame["source_path"] = str(path)
        frames.append(frame)
    if not frames:
        raise ValueError("kline_paths is empty")
    out = pd.concat(frames, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
    for col in ["open", "high", "low", "close", "volume"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["timestamp", "open", "high", "low", "close", "volume"])
    out["replay_date"] = out["timestamp"].dt.date.astype(str)
    return out.reset_index(drop=True)


def load_btcusdc_aggtrades(aggtrade_paths: Iterable[str | Path]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path_value in aggtrade_paths:
        path = Path(path_value)
        if path.suffix.lower() == ".zip":
            df = parse_binance_public_zip(path, data_type="aggTrades")
        else:
            df = pd.read_csv(path)
        missing = {"timestamp", "price", "quantity", "is_buyer_maker"}.difference(df.columns)
        if missing:
            raise ValueError(f"aggtrade file missing columns: {sorted(missing)}")
        frame = df.copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame["source_path"] = str(path)
        frames.append(frame)
    if not frames:
        raise ValueError("aggtrade_paths is empty")
    out = pd.concat(frames, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
    out["price"] = pd.to_numeric(out["price"], errors="coerce")
    out["quantity"] = pd.to_numeric(out["quantity"], errors="coerce")
    out["is_buyer_maker"] = out["is_buyer_maker"].astype(bool)
    return out.dropna(subset=["timestamp", "price", "quantity"]).reset_index(drop=True)


def aggregate_btcusdc_aggtrades_to_bars(aggtrades: pd.DataFrame, *, freq: str = "1min") -> pd.DataFrame:
    if aggtrades.empty:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "trade_count",
                "taker_buy_volume",
                "taker_sell_volume",
                "taker_buy_ratio",
                "signed_taker_imbalance",
                "replay_date",
            ]
        )
    frame = aggtrades.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame["quantity"] = pd.to_numeric(frame["quantity"], errors="coerce")
    frame["is_buyer_maker"] = frame["is_buyer_maker"].astype(bool)
    frame = frame.dropna(subset=["timestamp", "price", "quantity"]).sort_values("timestamp").reset_index(drop=True)
    frame["bar_time"] = frame["timestamp"].dt.floor(freq)
    frame["taker_buy_quantity"] = np.where(~frame["is_buyer_maker"], frame["quantity"], 0.0)
    frame["taker_sell_quantity"] = np.where(frame["is_buyer_maker"], frame["quantity"], 0.0)
    grouped = frame.groupby("bar_time", sort=True)
    bars = grouped.agg(
        open=("price", "first"),
        high=("price", "max"),
        low=("price", "min"),
        close=("price", "last"),
        volume=("quantity", "sum"),
        trade_count=("price", "size"),
        taker_buy_volume=("taker_buy_quantity", "sum"),
        taker_sell_volume=("taker_sell_quantity", "sum"),
    ).reset_index()
    bars = bars.rename(columns={"bar_time": "timestamp"})
    volume = pd.to_numeric(bars["volume"], errors="coerce").replace(0, np.nan)
    bars["taker_buy_ratio"] = (pd.to_numeric(bars["taker_buy_volume"], errors="coerce") / volume).fillna(0.0)
    bars["signed_taker_imbalance"] = (
        (pd.to_numeric(bars["taker_buy_volume"], errors="coerce") - pd.to_numeric(bars["taker_sell_volume"], errors="coerce")) / volume
    ).fillna(0.0)
    bars["replay_date"] = pd.to_datetime(bars["timestamp"], utc=True).dt.date.astype(str)
    return bars.reset_index(drop=True)


def build_candidate_trade_ledger(klines: pd.DataFrame, candidate: BTCUSDCCandidate) -> pd.DataFrame:
    frame = _candidate_frame(klines, candidate.lookback_minutes, candidate.horizon_minutes)
    return _build_candidate_trade_ledger_from_frame(frame, candidate)


def build_delayed_candidate_trade_ledger(klines: pd.DataFrame, candidate: BTCUSDCCandidate, *, entry_delay_minutes: int = 0) -> pd.DataFrame:
    delay = int(entry_delay_minutes)
    if delay < 0:
        raise ValueError("entry_delay_minutes must be non-negative")
    if delay == 0:
        trades = build_candidate_trade_ledger(klines, candidate)
        if not trades.empty:
            trades = trades.copy()
            trades["signal_timestamp"] = trades["timestamp"]
            trades["entry_delay_minutes"] = 0
        return trades

    frame = _candidate_frame(klines, candidate.lookback_minutes, candidate.horizon_minutes + delay)
    feature = pd.to_numeric(frame[candidate.filter_feature], errors="coerce")
    eligible = feature >= float(candidate.threshold)
    signals = _candidate_signals(frame, candidate.direction)
    eligible &= signals != 0
    max_index = len(frame) - 1
    valid_signal_index = np.arange(len(frame)) + delay + int(candidate.horizon_minutes) <= max_index
    eligible &= valid_signal_index
    keep_idx = _non_overlapping_indices(eligible, horizon=int(candidate.horizon_minutes))
    if keep_idx.size == 0:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "signal_timestamp",
                "replay_date",
                "signal",
                "entry_px",
                "exit_px",
                "gross_pnl_bps",
                "net_pnl_bps",
                "lookback_minutes",
                "horizon_minutes",
                "entry_delay_minutes",
                "direction",
                "filter_feature",
                "threshold",
                "fee_bps",
            ]
        )

    entry_idx = keep_idx + delay
    exit_idx = entry_idx + int(candidate.horizon_minutes)
    open_px = pd.to_numeric(frame["open"], errors="coerce").to_numpy(float)
    selected = frame.iloc[keep_idx].copy()
    selected_signal = signals.iloc[keep_idx].astype(int).to_numpy()
    entry_px = open_px[entry_idx]
    exit_px = open_px[exit_idx]
    gross = (exit_px / entry_px - 1.0) * 10000.0 * selected_signal
    trades = pd.DataFrame(
        {
            "timestamp": frame.iloc[entry_idx]["timestamp"].to_numpy(),
            "signal_timestamp": selected["timestamp"].to_numpy(),
            "replay_date": frame.iloc[entry_idx]["replay_date"].to_numpy(),
            "signal": selected_signal,
            "entry_px": entry_px,
            "exit_px": exit_px,
            "gross_pnl_bps": gross,
            "net_pnl_bps": gross - float(candidate.fee_bps),
            "lookback_return_bps": selected["lookback_return_bps"].to_numpy(float),
            "abs_return_bps": selected["abs_return_bps"].to_numpy(float),
            "range_bps": selected["range_bps"].to_numpy(float),
            "volume_ratio": selected["volume_ratio"].to_numpy(float),
            "flow_imbalance": selected.get("flow_imbalance", pd.Series(0.0, index=selected.index)).to_numpy(float),
            "abs_flow_imbalance": selected.get("abs_flow_imbalance", pd.Series(0.0, index=selected.index)).to_numpy(float),
            "lookback_minutes": int(candidate.lookback_minutes),
            "horizon_minutes": int(candidate.horizon_minutes),
            "entry_delay_minutes": delay,
            "direction": str(candidate.direction),
            "filter_feature": str(candidate.filter_feature),
            "threshold": float(candidate.threshold),
            "quantile": np.nan if candidate.quantile is None else float(candidate.quantile),
            "fee_bps": float(candidate.fee_bps),
        }
    )
    trades["equity_bps"] = pd.to_numeric(trades["net_pnl_bps"], errors="coerce").fillna(0.0).cumsum()
    return trades


def build_delayed_candidate_trade_ledger_grid(
    klines: pd.DataFrame,
    candidate: BTCUSDCCandidate,
    *,
    entry_delay_minutes: Iterable[int],
) -> pd.DataFrame:
    delays = sorted({int(delay) for delay in entry_delay_minutes})
    if any(delay < 0 for delay in delays):
        raise ValueError("entry_delay_minutes must be non-negative")
    ledgers: list[pd.DataFrame] = []
    for delay in delays:
        ledger = build_delayed_candidate_trade_ledger(klines, candidate, entry_delay_minutes=delay)
        if not ledger.empty:
            ledger = ledger.copy()
            ledger["entry_delay_minutes"] = int(delay)
        ledgers.append(ledger)
    return pd.concat(ledgers, ignore_index=True) if ledgers else pd.DataFrame()


def _build_candidate_trade_ledger_from_frame(frame: pd.DataFrame, candidate: BTCUSDCCandidate) -> pd.DataFrame:
    feature = pd.to_numeric(frame[candidate.filter_feature], errors="coerce")
    eligible = feature >= float(candidate.threshold)
    signals = _candidate_signals(frame, candidate.direction)
    eligible &= signals != 0
    eligible &= pd.to_numeric(frame["future_return_bps"], errors="coerce").notna()
    keep_idx = _non_overlapping_indices(eligible, horizon=int(candidate.horizon_minutes))
    if keep_idx.size == 0:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "replay_date",
                "signal",
                "entry_px",
                "exit_px",
                "gross_pnl_bps",
                "net_pnl_bps",
                "lookback_minutes",
                "horizon_minutes",
                "direction",
                "filter_feature",
                "threshold",
                "fee_bps",
            ]
        )
    selected = frame.iloc[keep_idx].copy()
    selected_signal = signals.iloc[keep_idx].astype(int).to_numpy()
    future_return = pd.to_numeric(selected["future_return_bps"], errors="coerce").to_numpy(float)
    gross = future_return * selected_signal
    trades = pd.DataFrame(
        {
            "timestamp": selected["timestamp"].to_numpy(),
            "replay_date": selected["replay_date"].to_numpy(),
            "signal": selected_signal,
            "entry_px": selected["open"].to_numpy(float),
            "exit_px": selected["future_exit_open"].to_numpy(float),
            "gross_pnl_bps": gross,
            "net_pnl_bps": gross - float(candidate.fee_bps),
            "lookback_return_bps": selected["lookback_return_bps"].to_numpy(float),
            "abs_return_bps": selected["abs_return_bps"].to_numpy(float),
            "range_bps": selected["range_bps"].to_numpy(float),
            "volume_ratio": selected["volume_ratio"].to_numpy(float),
            "flow_imbalance": selected.get("flow_imbalance", pd.Series(0.0, index=selected.index)).to_numpy(float),
            "abs_flow_imbalance": selected.get("abs_flow_imbalance", pd.Series(0.0, index=selected.index)).to_numpy(float),
            "lookback_minutes": int(candidate.lookback_minutes),
            "horizon_minutes": int(candidate.horizon_minutes),
            "direction": str(candidate.direction),
            "filter_feature": str(candidate.filter_feature),
            "threshold": float(candidate.threshold),
            "quantile": np.nan if candidate.quantile is None else float(candidate.quantile),
            "fee_bps": float(candidate.fee_bps),
        }
    )
    trades["equity_bps"] = pd.to_numeric(trades["net_pnl_bps"], errors="coerce").fillna(0.0).cumsum()
    return trades


def candidate_grid_from_calibration(
    calibration_klines: pd.DataFrame,
    *,
    lookbacks: Iterable[int],
    horizons: Iterable[int],
    directions: Iterable[str],
    filter_features: Iterable[str],
    quantiles: Iterable[float],
    fee_bps: float = 8.5,
) -> list[BTCUSDCCandidate]:
    candidates: list[BTCUSDCCandidate] = []
    for lookback in lookbacks:
        for horizon in horizons:
            frame = _candidate_frame(calibration_klines, int(lookback), int(horizon))
            for feature_name in filter_features:
                if feature_name not in frame.columns:
                    continue
                values = pd.to_numeric(frame[feature_name], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
                if values.empty:
                    continue
                thresholds = _dedupe_threshold_quantiles((float(values.quantile(float(q))), float(q)) for q in quantiles)
                for threshold, quantile in thresholds:
                    for direction in directions:
                        candidates.append(
                            BTCUSDCCandidate(
                                lookback_minutes=int(lookback),
                                horizon_minutes=int(horizon),
                                direction=str(direction),
                                filter_feature=str(feature_name),
                                threshold=float(threshold),
                                quantile=float(quantile),
                                fee_bps=float(fee_bps),
                            )
                        )
    return candidates


def evaluate_candidate_grid(
    calibration_klines: pd.DataFrame,
    validation_klines: pd.DataFrame,
    candidates: list[BTCUSDCCandidate],
    *,
    leverage: float = 8.0,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    cal_frames: dict[tuple[int, int], pd.DataFrame] = {}
    val_frames: dict[tuple[int, int], pd.DataFrame] = {}
    for candidate_id, candidate in enumerate(candidates):
        key = (int(candidate.lookback_minutes), int(candidate.horizon_minutes))
        if key not in cal_frames:
            cal_frames[key] = _candidate_frame(calibration_klines, key[0], key[1])
            val_frames[key] = _candidate_frame(validation_klines, key[0], key[1])
        cal = _build_candidate_trade_ledger_from_frame(cal_frames[key], candidate)
        val = _build_candidate_trade_ledger_from_frame(val_frames[key], candidate)
        row = {
            "candidate_id": int(candidate_id),
            **candidate.to_dict(),
            **_metric_prefix(cal, "calibration", leverage=leverage),
            **_metric_prefix(val, "validation", leverage=leverage),
            "candidate_json": json.dumps(candidate.to_dict(), sort_keys=True),
        }
        rows.append(row)
    return pd.DataFrame(rows)


def summarize_fixed_policy_stability(
    trades: pd.DataFrame,
    *,
    fold_col: str,
    delay_summary: pd.DataFrame,
    extra_cost_summary: pd.DataFrame,
    min_trades: int = 50,
    min_active_folds: int = 5,
    min_positive_fold_rate: float = 0.70,
    min_worst_fold_net_pnl_bps: float = -500.0,
    require_delay_total_positive: bool = True,
    required_positive_extra_cost_bps: float = 4.0,
) -> dict[str, object]:
    pnl = pd.to_numeric(trades.get("net_pnl_bps", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    if fold_col not in trades.columns:
        raise ValueError(f"trades missing fold column: {fold_col}")
    fold_totals = trades.assign(_pnl=pnl).groupby(fold_col, sort=True)["_pnl"].sum()
    positive_fold_rate = float((fold_totals > 0.0).mean()) if len(fold_totals) else 0.0
    delay_totals = pd.to_numeric(delay_summary.get("total_net_pnl_bps", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    extra_frame = extra_cost_summary.copy()
    extra_frame["extra_cost_bps"] = pd.to_numeric(extra_frame.get("extra_cost_bps", pd.Series(dtype=float)), errors="coerce")
    extra_frame["total_net_pnl_bps"] = pd.to_numeric(extra_frame.get("total_net_pnl_bps", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    required_extra = extra_frame.loc[extra_frame["extra_cost_bps"] <= float(required_positive_extra_cost_bps), "total_net_pnl_bps"]
    checks = {
        "positive_total_net_pnl": float(pnl.sum()) > 0.0,
        "min_trades": int(len(pnl)) >= int(min_trades),
        "min_active_folds": int(len(fold_totals)) >= int(min_active_folds),
        "positive_fold_rate": positive_fold_rate >= float(min_positive_fold_rate),
        "worst_fold_floor": (float(fold_totals.min()) if len(fold_totals) else 0.0) >= float(min_worst_fold_net_pnl_bps),
        "delay_total_positive": bool((delay_totals > 0.0).all()) if bool(require_delay_total_positive) and len(delay_totals) else not bool(require_delay_total_positive),
        "required_extra_cost_positive": bool((required_extra > 0.0).all()) if len(required_extra) else False,
    }
    return {
        "passed": bool(all(checks.values())),
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "trade_count": int(len(pnl)),
        "total_net_pnl_bps": float(pnl.sum()),
        "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
        "active_folds": int(len(fold_totals)),
        "positive_fold_rate": positive_fold_rate,
        "worst_fold_net_pnl_bps": float(fold_totals.min()) if len(fold_totals) else 0.0,
        "worst_delay_total_net_pnl_bps": float(delay_totals.min()) if len(delay_totals) else 0.0,
        "worst_extra_cost_total_net_pnl_bps": float(extra_frame["total_net_pnl_bps"].min()) if len(extra_frame) else 0.0,
    }


def summarize_delay_stress_grid(
    trades: pd.DataFrame,
    *,
    delay_col: str = "entry_delay_minutes",
    fold_col: str | None = None,
    min_positive_delay_rate: float = 1.0,
    min_worst_delay_total_net_pnl_bps: float = 0.0,
) -> dict[str, object]:
    required = {delay_col, "net_pnl_bps"}
    if fold_col is not None:
        required.add(fold_col)
    missing = required.difference(trades.columns)
    if missing:
        raise ValueError(f"trades missing columns: {sorted(missing)}")
    frame = trades.copy()
    frame[delay_col] = pd.to_numeric(frame[delay_col], errors="coerce").astype("Int64")
    frame["net_pnl_bps"] = pd.to_numeric(frame["net_pnl_bps"], errors="coerce").fillna(0.0)
    frame = frame.dropna(subset=[delay_col]).copy()
    rows: list[dict[str, object]] = []
    for delay, group in frame.groupby(delay_col, sort=True):
        pnl = pd.to_numeric(group["net_pnl_bps"], errors="coerce").fillna(0.0)
        row: dict[str, object] = {
            "entry_delay_minutes": int(delay),
            "trades": int(len(group)),
            "total_net_pnl_bps": float(pnl.sum()),
            "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
            "win_rate": float((pnl > 0.0).mean()) if len(pnl) else 0.0,
            "positive": bool(float(pnl.sum()) > 0.0),
        }
        if fold_col is not None:
            fold_totals = group.groupby(fold_col, sort=True)["net_pnl_bps"].sum()
            row["positive_fold_rate"] = float((fold_totals > 0.0).mean()) if len(fold_totals) else 0.0
            row["worst_fold_net_pnl_bps"] = float(fold_totals.min()) if len(fold_totals) else 0.0
        rows.append(row)
    totals = [float(row["total_net_pnl_bps"]) for row in rows]
    positive_rate = float(np.mean([total > 0.0 for total in totals])) if totals else 0.0
    worst_total = float(min(totals)) if totals else 0.0
    checks = {
        "has_delay_rows": bool(rows),
        "positive_delay_rate": positive_rate >= float(min_positive_delay_rate),
        "worst_delay_total_floor": worst_total >= float(min_worst_delay_total_net_pnl_bps),
    }
    return {
        "aggregate": {
            "passed": bool(all(checks.values())),
            "checks": checks,
            "failed_checks": [name for name, passed in checks.items() if not passed],
            "delay_count": int(len(rows)),
            "positive_delay_count": int(sum(total > 0.0 for total in totals)),
            "positive_delay_rate": positive_rate,
            "worst_delay_total_net_pnl_bps": worst_total,
            "best_delay_total_net_pnl_bps": float(max(totals)) if totals else 0.0,
        },
        "delays": rows,
    }


def summarize_cost_delay_surface(
    trades: pd.DataFrame,
    *,
    extra_cost_bps: Iterable[float],
    max_delay_minutes: Iterable[int],
    delay_col: str = "entry_delay_minutes",
    min_positive_delay_rate: float = 0.80,
    min_worst_delay_total_net_pnl_bps: float = 0.0,
) -> dict[str, object]:
    required = {delay_col, "net_pnl_bps"}
    missing = required.difference(trades.columns)
    if missing:
        raise ValueError(f"trades missing columns: {sorted(missing)}")
    frame = trades.copy()
    frame[delay_col] = pd.to_numeric(frame[delay_col], errors="coerce").astype("Int64")
    frame["net_pnl_bps"] = pd.to_numeric(frame["net_pnl_bps"], errors="coerce").fillna(0.0)
    frame = frame.dropna(subset=[delay_col]).copy()
    costs = sorted({float(x) for x in extra_cost_bps})
    max_delays = sorted({int(x) for x in max_delay_minutes})
    rows: list[dict[str, object]] = []
    for max_delay in max_delays:
        delay_frame = frame.loc[frame[delay_col].astype(int) <= int(max_delay)].copy()
        for cost in costs:
            adjusted = delay_frame.copy()
            adjusted["net_pnl_bps"] = pd.to_numeric(adjusted["net_pnl_bps"], errors="coerce").fillna(0.0) - float(cost)
            delay_totals = adjusted.groupby(delay_col, sort=True)["net_pnl_bps"].sum()
            totals = [float(x) for x in delay_totals.tolist()]
            positive_rate = float(np.mean([total > 0.0 for total in totals])) if totals else 0.0
            worst_total = float(min(totals)) if totals else 0.0
            checks = {
                "has_delay_rows": bool(totals),
                "positive_delay_rate": positive_rate >= float(min_positive_delay_rate),
                "worst_delay_total_floor": worst_total >= float(min_worst_delay_total_net_pnl_bps),
            }
            rows.append(
                {
                    "max_delay_minutes": int(max_delay),
                    "extra_cost_bps": float(cost),
                    "delay_count": int(len(totals)),
                    "trade_count": int(len(adjusted)),
                    "total_net_pnl_bps": float(adjusted["net_pnl_bps"].sum()),
                    "positive_delay_count": int(sum(total > 0.0 for total in totals)),
                    "positive_delay_rate": positive_rate,
                    "worst_delay_total_net_pnl_bps": worst_total,
                    "best_delay_total_net_pnl_bps": float(max(totals)) if totals else 0.0,
                    "passed": bool(all(checks.values())),
                    "failed_checks": ";".join(name for name, passed in checks.items() if not passed),
                }
            )
    passed = [row for row in rows if bool(row["passed"])]
    best = max(passed, key=lambda row: (int(row["max_delay_minutes"]), float(row["extra_cost_bps"]))) if passed else None
    return {
        "aggregate": {
            "surface_rows": int(len(rows)),
            "passed_rows": int(len(passed)),
            "has_passed_contract": bool(best is not None),
            "best_passed_max_delay_minutes": int(best["max_delay_minutes"]) if best is not None else None,
            "best_passed_extra_cost_bps": float(best["extra_cost_bps"]) if best is not None else None,
            "best_passed_worst_delay_total_net_pnl_bps": float(best["worst_delay_total_net_pnl_bps"]) if best is not None else None,
            "best_passed_positive_delay_rate": float(best["positive_delay_rate"]) if best is not None else None,
        },
        "rows": rows,
    }


def summarize_monthly_loss_cooldown(
    trades: pd.DataFrame,
    *,
    timestamp_col: str = "timestamp",
    pnl_col: str = "net_pnl_bps",
    trigger_negative_months: int = 1,
    cooldown_months: int = 1,
) -> dict[str, object]:
    required = {timestamp_col, pnl_col}
    missing = required.difference(trades.columns)
    if missing:
        raise ValueError(f"trades missing columns: {sorted(missing)}")
    if int(trigger_negative_months) < 1:
        raise ValueError("trigger_negative_months must be positive")
    if int(cooldown_months) < 0:
        raise ValueError("cooldown_months must be non-negative")
    frame = trades.copy()
    frame[timestamp_col] = pd.to_datetime(frame[timestamp_col], utc=True)
    frame[pnl_col] = pd.to_numeric(frame[pnl_col], errors="coerce").fillna(0.0)
    frame = frame.dropna(subset=[timestamp_col]).sort_values(timestamp_col).reset_index(drop=True)
    if frame.empty:
        return {
            "aggregate": {
                "months": 0,
                "traded_months": 0,
                "risk_off_months": 0,
                "trades": 0,
                "skipped_trades": 0,
                "total_net_pnl_bps": 0.0,
                "raw_total_net_pnl_bps": 0.0,
                "positive_month_rate": 0.0,
                "worst_month_net_pnl_bps": 0.0,
            },
            "months": [],
        }
    month_values = frame[timestamp_col].dt.tz_convert(None)
    frame["month"] = month_values.dt.to_period("M").astype(str)
    month_index = pd.period_range(month_values.min().to_period("M"), month_values.max().to_period("M"), freq="M")
    cooldown_remaining = 0
    consecutive_negative = 0
    rows: list[dict[str, object]] = []
    for period in month_index:
        month = str(period)
        group = frame.loc[frame["month"] == month].copy()
        raw_pnl = float(group[pnl_col].sum()) if not group.empty else 0.0
        raw_trades = int(len(group))
        risk_off = cooldown_remaining > 0
        if risk_off:
            realized_pnl = 0.0
            kept_trades = 0
            skipped_trades = raw_trades
            cooldown_remaining -= 1
        else:
            realized_pnl = raw_pnl
            kept_trades = raw_trades
            skipped_trades = 0
            if raw_trades > 0 and realized_pnl < 0.0:
                consecutive_negative += 1
            elif raw_trades > 0:
                consecutive_negative = 0
            if consecutive_negative >= int(trigger_negative_months):
                cooldown_remaining = int(cooldown_months)
                consecutive_negative = 0
        rows.append(
            {
                "month": month,
                "risk_off": bool(risk_off),
                "raw_trades": raw_trades,
                "kept_trades": int(kept_trades),
                "skipped_trades": int(skipped_trades),
                "raw_net_pnl_bps": raw_pnl,
                "net_pnl_bps": float(realized_pnl),
                "positive": bool(realized_pnl > 0.0),
            }
        )
    traded_rows = [row for row in rows if int(row["kept_trades"]) > 0]
    traded_pnl = [float(row["net_pnl_bps"]) for row in traded_rows]
    return {
        "aggregate": {
            "months": int(len(rows)),
            "traded_months": int(len(traded_rows)),
            "risk_off_months": int(sum(bool(row["risk_off"]) for row in rows)),
            "trades": int(sum(int(row["kept_trades"]) for row in rows)),
            "skipped_trades": int(sum(int(row["skipped_trades"]) for row in rows)),
            "total_net_pnl_bps": float(sum(float(row["net_pnl_bps"]) for row in rows)),
            "raw_total_net_pnl_bps": float(sum(float(row["raw_net_pnl_bps"]) for row in rows)),
            "positive_month_rate": float(np.mean([value > 0.0 for value in traded_pnl])) if traded_pnl else 0.0,
            "worst_month_net_pnl_bps": float(min(traded_pnl)) if traded_pnl else 0.0,
        },
        "months": rows,
    }


def summarize_delay_monthly_cooldown_grid(
    trades: pd.DataFrame,
    *,
    extra_cost_bps: float = 0.0,
    max_delay_minutes: int,
    trigger_negative_months: int,
    cooldown_months: int,
    delay_col: str = "entry_delay_minutes",
    fold_col: str = "fold",
    holdout_folds: Iterable[int] | None = None,
) -> dict[str, object]:
    required = {"timestamp", "net_pnl_bps", delay_col}
    missing = required.difference(trades.columns)
    if missing:
        raise ValueError(f"trades missing columns: {sorted(missing)}")
    frame = trades.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame[delay_col] = pd.to_numeric(frame[delay_col], errors="coerce").astype("Int64")
    frame["net_pnl_bps"] = pd.to_numeric(frame["net_pnl_bps"], errors="coerce").fillna(0.0) - float(extra_cost_bps)
    frame = frame.dropna(subset=[delay_col]).copy()
    frame = frame.loc[frame[delay_col].astype(int) <= int(max_delay_minutes)].copy()
    if fold_col in frame.columns:
        frame[fold_col] = pd.to_numeric(frame[fold_col], errors="coerce").astype("Int64")
    holdout_set = {int(x) for x in holdout_folds} if holdout_folds is not None else set()
    rows: list[dict[str, object]] = []
    kept_ledgers: list[pd.DataFrame] = []
    for delay, group in frame.groupby(delay_col, sort=True):
        delay_value = int(delay)
        result = summarize_monthly_loss_cooldown(
            group,
            trigger_negative_months=trigger_negative_months,
            cooldown_months=cooldown_months,
        )
        month_rows = pd.DataFrame(result["months"])
        risk_off_months = set(month_rows.loc[month_rows["risk_off"].astype(bool), "month"].astype(str).tolist()) if not month_rows.empty else set()
        kept = group.copy()
        month_values = kept["timestamp"].dt.tz_convert(None)
        kept["month"] = month_values.dt.to_period("M").astype(str)
        kept = kept.loc[~kept["month"].astype(str).isin(risk_off_months)].copy()
        kept_ledgers.append(kept)
        agg = result["aggregate"]
        holdout_total = 0.0
        holdout_positive_fold_rate = 0.0
        holdout_active_folds = 0
        if holdout_set and fold_col in kept.columns:
            holdout = kept.loc[kept[fold_col].astype(int).isin(holdout_set)].copy()
            holdout_fold_totals = holdout.groupby(fold_col, sort=True)["net_pnl_bps"].sum() if not holdout.empty else pd.Series(dtype=float)
            holdout_total = float(holdout_fold_totals.sum()) if len(holdout_fold_totals) else 0.0
            holdout_positive_fold_rate = float((holdout_fold_totals > 0.0).mean()) if len(holdout_fold_totals) else 0.0
            holdout_active_folds = int(len(holdout_fold_totals))
        rows.append(
            {
                "entry_delay_minutes": delay_value,
                "trades": int(agg["trades"]),
                "skipped_trades": int(agg["skipped_trades"]),
                "total_net_pnl_bps": float(agg["total_net_pnl_bps"]),
                "raw_total_net_pnl_bps": float(agg["raw_total_net_pnl_bps"]),
                "positive_month_rate": float(agg["positive_month_rate"]),
                "worst_month_net_pnl_bps": float(agg["worst_month_net_pnl_bps"]),
                "holdout_total_net_pnl_bps": holdout_total,
                "holdout_positive_fold_rate": holdout_positive_fold_rate,
                "holdout_active_folds": holdout_active_folds,
                "positive": bool(float(agg["total_net_pnl_bps"]) > 0.0),
            }
        )
    totals = [float(row["total_net_pnl_bps"]) for row in rows]
    holdout_totals = [float(row["holdout_total_net_pnl_bps"]) for row in rows]
    kept_ledger = pd.concat(kept_ledgers, ignore_index=True) if kept_ledgers else pd.DataFrame()
    return {
        "aggregate": {
            "delay_count": int(len(rows)),
            "positive_delay_count": int(sum(total > 0.0 for total in totals)),
            "positive_delay_rate": float(np.mean([total > 0.0 for total in totals])) if totals else 0.0,
            "total_net_pnl_bps": float(sum(totals)),
            "worst_delay_total_net_pnl_bps": float(min(totals)) if totals else 0.0,
            "best_delay_total_net_pnl_bps": float(max(totals)) if totals else 0.0,
            "holdout_positive_delay_rate": float(np.mean([total > 0.0 for total in holdout_totals])) if holdout_totals else 0.0,
            "worst_holdout_delay_total_net_pnl_bps": float(min(holdout_totals)) if holdout_totals else 0.0,
        },
        "delays": rows,
        "kept_ledger": kept_ledger,
    }


def select_delay_monthly_cooldown_policy(policy_scan: pd.DataFrame) -> pd.Series:
    if policy_scan.empty:
        raise ValueError("policy_scan is empty")
    required = {
        "trigger_negative_months",
        "cooldown_months",
        "design_positive_delay_rate",
        "design_worst_delay_total_net_pnl_bps",
        "design_total_net_pnl_bps",
    }
    missing = required.difference(policy_scan.columns)
    if missing:
        raise ValueError(f"policy_scan missing columns: {sorted(missing)}")
    frame = policy_scan.copy()
    frame["trigger_negative_months"] = pd.to_numeric(frame["trigger_negative_months"], errors="coerce").astype("Int64")
    frame["cooldown_months"] = pd.to_numeric(frame["cooldown_months"], errors="coerce").astype("Int64")
    for col in ["design_positive_delay_rate", "design_worst_delay_total_net_pnl_bps", "design_total_net_pnl_bps"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(-np.inf)
    frame = frame.dropna(subset=["trigger_negative_months", "cooldown_months"]).copy()
    if frame.empty:
        raise ValueError("no valid policy rows")
    frame = frame.sort_values(
        [
            "design_positive_delay_rate",
            "design_worst_delay_total_net_pnl_bps",
            "design_total_net_pnl_bps",
            "trigger_negative_months",
            "cooldown_months",
        ],
        ascending=[False, False, False, True, True],
    )
    return frame.iloc[0]


def summarize_holdout_failure_attribution(
    trades: pd.DataFrame,
    *,
    holdout_folds: Iterable[int],
    timestamp_col: str = "timestamp",
    fold_col: str = "fold",
    delay_col: str = "entry_delay_minutes",
    pnl_col: str = "net_pnl_bps",
) -> dict[str, object]:
    required = {timestamp_col, fold_col, delay_col, pnl_col}
    missing = required.difference(trades.columns)
    if missing:
        raise ValueError(f"trades missing columns: {sorted(missing)}")
    holdout_set = {int(x) for x in holdout_folds}
    if not holdout_set:
        raise ValueError("holdout_folds is empty")
    frame = trades.copy()
    frame[timestamp_col] = pd.to_datetime(frame[timestamp_col], utc=True)
    frame[fold_col] = pd.to_numeric(frame[fold_col], errors="coerce").astype("Int64")
    frame[delay_col] = pd.to_numeric(frame[delay_col], errors="coerce").astype("Int64")
    frame[pnl_col] = pd.to_numeric(frame[pnl_col], errors="coerce").fillna(0.0)
    frame = frame.dropna(subset=[timestamp_col, fold_col, delay_col]).copy()
    frame = frame.loc[frame[fold_col].astype(int).isin(holdout_set)].copy()
    if frame.empty:
        empty = {
            "aggregate": {
                "holdout_folds": sorted(holdout_set),
                "holdout_trades": 0,
                "holdout_total_net_pnl_bps": 0.0,
                "negative_fold_count": 0,
                "negative_month_count": 0,
                "negative_hour_count": 0,
                "negative_delay_count": 0,
                "worst_fold_net_pnl_bps": 0.0,
                "worst_month_net_pnl_bps": 0.0,
                "worst_hour_net_pnl_bps": 0.0,
                "worst_delay_net_pnl_bps": 0.0,
            },
            "by_fold": [],
            "by_month": [],
            "by_hour": [],
            "by_delay": [],
        }
        return empty
    frame["month"] = frame[timestamp_col].dt.tz_convert(None).dt.to_period("M").astype(str)
    frame["hour"] = frame[timestamp_col].dt.hour.astype(int)

    def _breakout(group_col: str, out_col: str) -> list[dict[str, object]]:
        grouped = frame.groupby(group_col, sort=True).agg(trades=(pnl_col, "size"), total_net_pnl_bps=(pnl_col, "sum"))
        negative_loss = float((-grouped["total_net_pnl_bps"].clip(upper=0.0)).sum())
        rows: list[dict[str, object]] = []
        for key, row in grouped.reset_index().iterrows():
            value = row[group_col]
            total = float(row["total_net_pnl_bps"])
            loss = float(max(-total, 0.0))
            rows.append(
                {
                    out_col: int(value) if group_col in {fold_col, delay_col, "hour"} else str(value),
                    "trades": int(row["trades"]),
                    "total_net_pnl_bps": total,
                    "negative": bool(total < 0.0),
                    "negative_loss_bps": loss,
                    "negative_loss_share": float(loss / negative_loss) if negative_loss > 0.0 else 0.0,
                }
            )
        return sorted(rows, key=lambda item: (float(item["total_net_pnl_bps"]), item[out_col]))

    by_fold = _breakout(fold_col, "fold")
    by_month = _breakout("month", "month")
    by_hour = _breakout("hour", "hour")
    by_delay = _breakout(delay_col, "entry_delay_minutes")

    def _negative_count(rows: list[dict[str, object]]) -> int:
        return int(sum(bool(row["negative"]) for row in rows))

    def _worst(rows: list[dict[str, object]]) -> float:
        return float(min((float(row["total_net_pnl_bps"]) for row in rows), default=0.0))

    return {
        "aggregate": {
            "holdout_folds": sorted(holdout_set),
            "holdout_trades": int(len(frame)),
            "holdout_total_net_pnl_bps": float(frame[pnl_col].sum()),
            "negative_fold_count": _negative_count(by_fold),
            "negative_month_count": _negative_count(by_month),
            "negative_hour_count": _negative_count(by_hour),
            "negative_delay_count": _negative_count(by_delay),
            "worst_fold_net_pnl_bps": _worst(by_fold),
            "worst_month_net_pnl_bps": _worst(by_month),
            "worst_hour_net_pnl_bps": _worst(by_hour),
            "worst_delay_net_pnl_bps": _worst(by_delay),
        },
        "by_fold": by_fold,
        "by_month": by_month,
        "by_hour": by_hour,
        "by_delay": by_delay,
    }


def summarize_bucket_transfer_stability(
    trades: pd.DataFrame,
    *,
    bucket_col: str,
    design_folds: Iterable[int],
    holdout_folds: Iterable[int],
    fold_col: str = "fold",
    pnl_col: str = "net_pnl_bps",
) -> dict[str, object]:
    required = {bucket_col, fold_col, pnl_col}
    missing = required.difference(trades.columns)
    if missing:
        raise ValueError(f"trades missing columns: {sorted(missing)}")
    design_set = {int(x) for x in design_folds}
    holdout_set = {int(x) for x in holdout_folds}
    if not design_set:
        raise ValueError("design_folds is empty")
    if not holdout_set:
        raise ValueError("holdout_folds is empty")
    frame = trades.copy()
    frame[fold_col] = pd.to_numeric(frame[fold_col], errors="coerce").astype("Int64")
    frame[pnl_col] = pd.to_numeric(frame[pnl_col], errors="coerce").fillna(0.0)
    frame = frame.dropna(subset=[bucket_col, fold_col]).copy()
    design = frame.loc[frame[fold_col].astype(int).isin(design_set)].copy()
    holdout = frame.loc[frame[fold_col].astype(int).isin(holdout_set)].copy()
    design_totals = design.groupby(bucket_col, sort=True)[pnl_col].sum()
    holdout_totals = holdout.groupby(bucket_col, sort=True)[pnl_col].sum()
    combined = pd.DataFrame({"design_total_net_pnl_bps": design_totals, "holdout_total_net_pnl_bps": holdout_totals}).fillna(0.0)
    rows: list[dict[str, object]] = []
    for bucket, row in combined.reset_index().iterrows():
        bucket_value = row[bucket_col]
        design_total = float(row["design_total_net_pnl_bps"])
        holdout_total = float(row["holdout_total_net_pnl_bps"])
        design_sign = int(np.sign(design_total))
        holdout_sign = int(np.sign(holdout_total))
        rows.append(
            {
                "bucket": int(bucket_value) if pd.api.types.is_number(bucket_value) else str(bucket_value),
                "design_total_net_pnl_bps": design_total,
                "holdout_total_net_pnl_bps": holdout_total,
                "design_sign": design_sign,
                "holdout_sign": holdout_sign,
                "sign_agrees": bool(design_sign == holdout_sign),
            }
        )
    design_positive = [row for row in rows if int(row["design_sign"]) > 0]
    design_negative = [row for row in rows if int(row["design_sign"]) < 0]
    sign_agreements = [bool(row["sign_agrees"]) for row in rows]
    rank_corr = combined["design_total_net_pnl_bps"].corr(combined["holdout_total_net_pnl_bps"], method="spearman") if len(combined) >= 2 else np.nan
    return {
        "aggregate": {
            "bucket_col": bucket_col,
            "design_folds": sorted(design_set),
            "holdout_folds": sorted(holdout_set),
            "bucket_count": int(len(rows)),
            "design_positive_bucket_count": int(len(design_positive)),
            "design_negative_bucket_count": int(len(design_negative)),
            "holdout_positive_bucket_count": int(sum(int(row["holdout_sign"]) > 0 for row in rows)),
            "holdout_negative_bucket_count": int(sum(int(row["holdout_sign"]) < 0 for row in rows)),
            "sign_agreement_rate": float(np.mean(sign_agreements)) if sign_agreements else 0.0,
            "design_positive_holdout_positive_rate": float(np.mean([int(row["holdout_sign"]) > 0 for row in design_positive])) if design_positive else 0.0,
            "design_negative_holdout_negative_rate": float(np.mean([int(row["holdout_sign"]) < 0 for row in design_negative])) if design_negative else 0.0,
            "spearman_rank_correlation": float(rank_corr) if pd.notna(rank_corr) else 0.0,
        },
        "buckets": rows,
    }


def apply_prequential_bucket_guard(
    trades: pd.DataFrame,
    *,
    bucket_col: str,
    group_cols: Iterable[str] = ("entry_delay_minutes",),
    timestamp_col: str = "timestamp",
    pnl_col: str = "net_pnl_bps",
    min_history_trades: int = 1,
    min_cumulative_pnl_bps: float = 0.0,
    cold_start_keep: bool = True,
) -> pd.DataFrame:
    groups = list(group_cols)
    required = {bucket_col, timestamp_col, pnl_col, *groups}
    missing = required.difference(trades.columns)
    if missing:
        raise ValueError(f"trades missing columns: {sorted(missing)}")
    if int(min_history_trades) < 1:
        raise ValueError("min_history_trades must be positive")
    frame = trades.copy()
    frame[timestamp_col] = pd.to_datetime(frame[timestamp_col], utc=True)
    frame[pnl_col] = pd.to_numeric(frame[pnl_col], errors="coerce").fillna(0.0)
    frame = frame.dropna(subset=[bucket_col, timestamp_col]).copy()
    frame["_orig_index"] = np.arange(len(frame))
    rows: list[dict[str, object]] = []

    def _process_group(group: pd.DataFrame) -> None:
        state: dict[object, dict[str, float]] = {}
        ordered = group.sort_values([timestamp_col, "_orig_index"], kind="mergesort")
        for _, row in ordered.iterrows():
            bucket = row[bucket_col]
            prior = state.get(bucket, {"trades": 0.0, "pnl": 0.0})
            prior_trades = int(prior["trades"])
            prior_pnl = float(prior["pnl"])
            keep = bool(cold_start_keep) if prior_trades < int(min_history_trades) else prior_pnl > float(min_cumulative_pnl_bps)
            out = row.to_dict()
            out["guard_prior_trades"] = prior_trades
            out["guard_prior_pnl_bps"] = prior_pnl
            out["guard_keep"] = keep
            rows.append(out)
            if keep:
                state[bucket] = {
                    "trades": float(prior_trades + 1),
                    "pnl": prior_pnl + float(row[pnl_col]),
                }

    if groups:
        for _, group in frame.groupby(groups, sort=True, dropna=False):
            _process_group(group)
    else:
        _process_group(frame)
    guarded = pd.DataFrame(rows).sort_values("_orig_index", kind="mergesort").drop(columns=["_orig_index"]).reset_index(drop=True)
    guarded["guard_prior_trades"] = pd.to_numeric(guarded["guard_prior_trades"], errors="coerce").fillna(0).astype(int)
    guarded["guard_prior_pnl_bps"] = pd.to_numeric(guarded["guard_prior_pnl_bps"], errors="coerce").fillna(0.0)
    guarded["guard_keep"] = guarded["guard_keep"].astype(bool)
    return guarded


def summarize_route_closure_decision(evidence: Iterable[dict[str, object]]) -> dict[str, object]:
    rows = [dict(row) for row in evidence]
    if not rows:
        raise ValueError("evidence is empty")
    normalized: list[dict[str, object]] = []
    for row in rows:
        if "gate" not in row or "passed" not in row:
            raise ValueError("each evidence row must include gate and passed")
        normalized.append(
            {
                **row,
                "gate": str(row["gate"]),
                "passed": bool(row["passed"]),
                "required": bool(row.get("required", True)),
            }
        )
    failed_required = [str(row["gate"]) for row in normalized if bool(row["required"]) and not bool(row["passed"])]
    failed_optional = [str(row["gate"]) for row in normalized if not bool(row["required"]) and not bool(row["passed"])]
    promote = len(failed_required) == 0
    return {
        "promote_route": bool(promote),
        "route_closed": bool(not promote),
        "gate_count": int(len(normalized)),
        "required_gate_count": int(sum(bool(row["required"]) for row in normalized)),
        "passed_required_gate_count": int(sum(bool(row["required"]) and bool(row["passed"]) for row in normalized)),
        "failed_required_gates": failed_required,
        "failed_optional_gates": failed_optional,
        "evidence": normalized,
    }


def summarize_route_inventory_decision(routes: Iterable[dict[str, object]]) -> dict[str, object]:
    rows = [dict(row) for row in routes]
    if not rows:
        raise ValueError("routes is empty")
    normalized: list[dict[str, object]] = []
    for row in rows:
        if "route" not in row:
            raise ValueError("each route row must include route")
        status = str(row.get("status", "needs_validation"))
        promoted = bool(row.get("promoted", status == "promoted"))
        normalized.append({**row, "route": str(row["route"]), "status": status, "promoted": promoted})
    promoted_routes = [row["route"] for row in normalized if bool(row["promoted"]) or str(row["status"]) == "promoted"]
    closed_routes = [row["route"] for row in normalized if str(row["status"]) == "closed"]
    needs_validation_routes = [row["route"] for row in normalized if str(row["status"]) == "needs_validation"]
    if promoted_routes:
        next_action = "advance_promoted_route"
    elif needs_validation_routes:
        next_action = "validate_or_create_new_hypothesis"
    else:
        next_action = "create_new_hypothesis"
    return {
        "route_count": int(len(normalized)),
        "promoted_routes": promoted_routes,
        "needs_validation_routes": needs_validation_routes,
        "closed_routes": closed_routes,
        "next_action": next_action,
        "routes": normalized,
    }


def summarize_fixed_family_viability(
    evaluations: pd.DataFrame,
    *,
    group_columns: Iterable[str] = ("lookback_minutes", "horizon_minutes", "direction", "filter_feature", "quantile"),
    fold_col: str = "fold",
    trades_col: str = "validation_trades",
    pnl_col: str = "validation_total_net_pnl_bps",
    account_return_col: str = "validation_account_return_pct",
    min_active_folds: int = 10,
    min_positive_fold_rate: float = 0.70,
    min_total_account_return_pct: float = 0.0,
    min_worst_fold_account_return_pct: float = -50.0,
    min_median_fold_account_return_pct: float = 0.0,
) -> dict[str, object]:
    groups = list(group_columns)
    required = {fold_col, trades_col, pnl_col, account_return_col, *groups}
    missing = required.difference(evaluations.columns)
    if missing:
        raise ValueError(f"evaluations missing columns: {sorted(missing)}")
    if int(min_active_folds) < 1:
        raise ValueError("min_active_folds must be positive")

    frame = evaluations.copy()
    frame[fold_col] = pd.to_numeric(frame[fold_col], errors="coerce").astype("Int64")
    frame[trades_col] = pd.to_numeric(frame[trades_col], errors="coerce").fillna(0.0)
    frame[pnl_col] = pd.to_numeric(frame[pnl_col], errors="coerce").fillna(0.0)
    frame[account_return_col] = pd.to_numeric(frame[account_return_col], errors="coerce").fillna(0.0)
    frame = frame.dropna(subset=[fold_col]).copy()

    family_rows: list[dict[str, object]] = []
    for key, group in frame.groupby(groups, sort=True, dropna=False):
        key_values = key if isinstance(key, tuple) else (key,)
        active = group.loc[group[trades_col] > 0].copy()
        if active.empty:
            fold_metrics = pd.DataFrame(columns=[fold_col, trades_col, pnl_col, account_return_col])
        else:
            fold_metrics = (
                active.groupby(fold_col, sort=True)
                .agg(
                    validation_trades=(trades_col, "sum"),
                    validation_total_net_pnl_bps=(pnl_col, "sum"),
                    validation_account_return_pct=(account_return_col, "sum"),
                )
                .reset_index()
            )
        account_values = pd.to_numeric(fold_metrics["validation_account_return_pct"], errors="coerce").fillna(0.0)
        total_account = float(account_values.sum()) if len(account_values) else 0.0
        total_pnl = float(pd.to_numeric(fold_metrics["validation_total_net_pnl_bps"], errors="coerce").fillna(0.0).sum()) if len(fold_metrics) else 0.0
        positive_rate = float((account_values > 0.0).mean()) if len(account_values) else 0.0
        worst_fold = float(account_values.min()) if len(account_values) else 0.0
        median_fold = float(account_values.median()) if len(account_values) else 0.0
        checks = {
            "min_active_folds": int(len(fold_metrics)) >= int(min_active_folds),
            "positive_fold_rate": positive_rate >= float(min_positive_fold_rate),
            "positive_total_account_return": total_account > float(min_total_account_return_pct),
            "worst_fold_floor": worst_fold >= float(min_worst_fold_account_return_pct),
            "median_fold_floor": median_fold > float(min_median_fold_account_return_pct),
        }
        family_rows.append(
            {
                **{str(col): value for col, value in zip(groups, key_values, strict=True)},
                "active_folds": int(len(fold_metrics)),
                "validation_trades": int(pd.to_numeric(fold_metrics["validation_trades"], errors="coerce").fillna(0.0).sum()) if len(fold_metrics) else 0,
                "total_validation_net_pnl_bps": total_pnl,
                "total_validation_account_return_pct": total_account,
                "positive_fold_rate": positive_rate,
                "worst_fold_account_return_pct": worst_fold,
                "median_fold_account_return_pct": median_fold,
                "passed": bool(all(checks.values())),
                "meets_min_active_folds": bool(checks["min_active_folds"]),
                "failed_checks": ";".join(name for name, passed in checks.items() if not passed),
            }
        )

    family_rows = sorted(
        family_rows,
        key=lambda row: (
            bool(row["passed"]),
            bool(row["meets_min_active_folds"]),
            float(row["positive_fold_rate"]),
            float(row["worst_fold_account_return_pct"]),
            float(row["median_fold_account_return_pct"]),
            float(row["total_validation_account_return_pct"]),
        ),
        reverse=True,
    )
    passed_rows = [row for row in family_rows if bool(row["passed"])]
    best = family_rows[0] if family_rows else None
    aggregate_checks = {
        "has_families": bool(family_rows),
        "no_family_passed": bool(passed_rows),
    }
    return {
        "aggregate": {
            "family_count": int(len(family_rows)),
            "passed_family_count": int(len(passed_rows)),
            "promote_fixed_family": bool(passed_rows),
            "best_positive_fold_rate": float(best["positive_fold_rate"]) if best is not None else 0.0,
            "best_total_validation_account_return_pct": float(best["total_validation_account_return_pct"]) if best is not None else 0.0,
            "best_worst_fold_account_return_pct": float(best["worst_fold_account_return_pct"]) if best is not None else 0.0,
            "best_family": best,
            "checks": aggregate_checks,
            "failed_checks": [name for name, passed in aggregate_checks.items() if not passed],
        },
        "families": family_rows,
    }


def summarize_signal_inversion_viability(
    trades: pd.DataFrame,
    *,
    timestamp_col: str = "timestamp",
    fold_col: str = "fold",
    gross_col: str = "gross_pnl_bps",
    cost_col: str = "cost_bps",
    net_col: str = "net_pnl_bps",
    min_total_net_pnl_bps: float = 0.0,
    min_positive_fold_rate: float = 1.0,
    min_positive_month_rate: float = 1.0,
    min_win_rate: float = 0.50,
) -> dict[str, object]:
    required = {timestamp_col, fold_col, gross_col, cost_col, net_col}
    missing = required.difference(trades.columns)
    if missing:
        raise ValueError(f"trades missing columns: {sorted(missing)}")
    frame = trades.copy()
    frame[timestamp_col] = pd.to_datetime(frame[timestamp_col], utc=True)
    frame[fold_col] = pd.to_numeric(frame[fold_col], errors="coerce").astype("Int64")
    frame[gross_col] = pd.to_numeric(frame[gross_col], errors="coerce").fillna(0.0)
    frame[cost_col] = pd.to_numeric(frame[cost_col], errors="coerce").fillna(0.0)
    frame[net_col] = pd.to_numeric(frame[net_col], errors="coerce").fillna(0.0)
    frame = frame.dropna(subset=[timestamp_col, fold_col]).copy()
    frame["inverted_net_pnl_bps"] = -frame[gross_col] - frame[cost_col]

    def _metrics(pnl_col: str) -> dict[str, object]:
        pnl = pd.to_numeric(frame[pnl_col], errors="coerce").fillna(0.0)
        fold_totals = frame.assign(_pnl=pnl).groupby(fold_col, sort=True)["_pnl"].sum()
        month_frame = frame.assign(month=frame[timestamp_col].dt.tz_convert(None).dt.to_period("M").astype(str), _pnl=pnl)
        month_totals = month_frame.groupby("month", sort=True)["_pnl"].sum()
        return {
            "trades": int(len(frame)),
            "total_net_pnl_bps": float(pnl.sum()),
            "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
            "win_rate": float((pnl > 0.0).mean()) if len(pnl) else 0.0,
            "fold_count": int(len(fold_totals)),
            "positive_fold_rate": float((fold_totals > 0.0).mean()) if len(fold_totals) else 0.0,
            "worst_fold_net_pnl_bps": float(fold_totals.min()) if len(fold_totals) else 0.0,
            "month_count": int(len(month_totals)),
            "positive_month_rate": float((month_totals > 0.0).mean()) if len(month_totals) else 0.0,
            "worst_month_net_pnl_bps": float(month_totals.min()) if len(month_totals) else 0.0,
        }

    original = _metrics(net_col)
    inverted = _metrics("inverted_net_pnl_bps")
    checks = {
        "total_net_pnl": float(inverted["total_net_pnl_bps"]) >= float(min_total_net_pnl_bps),
        "positive_fold_rate": float(inverted["positive_fold_rate"]) >= float(min_positive_fold_rate),
        "positive_month_rate": float(inverted["positive_month_rate"]) >= float(min_positive_month_rate),
        "win_rate": float(inverted["win_rate"]) >= float(min_win_rate),
    }
    return {
        "aggregate": {
            "promote_inverted_signal": bool(all(checks.values())),
            "checks": checks,
            "failed_checks": [name for name, passed in checks.items() if not passed],
        },
        "original": original,
        "inverted": inverted,
    }


def summarize_cost_edge_viability(
    trades: pd.DataFrame,
    *,
    cost_bps_values: Iterable[float],
    variants: Iterable[str] = ("original", "inverted"),
    timestamp_col: str = "timestamp",
    fold_col: str = "fold",
    gross_col: str = "gross_pnl_bps",
    min_total_net_pnl_bps: float = 0.0,
    min_positive_fold_rate: float = 1.0,
    min_positive_month_rate: float = 1.0,
    min_win_rate: float = 0.50,
) -> dict[str, object]:
    required = {timestamp_col, fold_col, gross_col}
    missing = required.difference(trades.columns)
    if missing:
        raise ValueError(f"trades missing columns: {sorted(missing)}")
    costs = sorted({float(value) for value in cost_bps_values})
    if not costs:
        raise ValueError("cost_bps_values is empty")
    variant_values = [str(value) for value in variants]
    if not variant_values:
        raise ValueError("variants is empty")
    invalid = [value for value in variant_values if value not in {"original", "inverted"}]
    if invalid:
        raise ValueError(f"unsupported variants: {invalid}")

    frame = trades.copy()
    frame[timestamp_col] = pd.to_datetime(frame[timestamp_col], utc=True)
    frame[fold_col] = pd.to_numeric(frame[fold_col], errors="coerce").astype("Int64")
    frame[gross_col] = pd.to_numeric(frame[gross_col], errors="coerce").fillna(0.0)
    frame = frame.dropna(subset=[timestamp_col, fold_col]).copy()
    frame["month"] = frame[timestamp_col].dt.tz_convert(None).dt.to_period("M").astype(str)

    rows: list[dict[str, object]] = []
    for variant in variant_values:
        gross = frame[gross_col] if variant == "original" else -frame[gross_col]
        for cost in costs:
            pnl = gross - float(cost)
            fold_totals = frame.assign(_pnl=pnl).groupby(fold_col, sort=True)["_pnl"].sum()
            month_totals = frame.assign(_pnl=pnl).groupby("month", sort=True)["_pnl"].sum()
            total = float(pnl.sum())
            win_rate = float((pnl > 0.0).mean()) if len(pnl) else 0.0
            positive_fold_rate = float((fold_totals > 0.0).mean()) if len(fold_totals) else 0.0
            positive_month_rate = float((month_totals > 0.0).mean()) if len(month_totals) else 0.0
            checks = {
                "total_net_pnl": total >= float(min_total_net_pnl_bps),
                "positive_fold_rate": positive_fold_rate >= float(min_positive_fold_rate),
                "positive_month_rate": positive_month_rate >= float(min_positive_month_rate),
                "win_rate": win_rate >= float(min_win_rate),
            }
            rows.append(
                {
                    "variant": variant,
                    "cost_bps": float(cost),
                    "trades": int(len(frame)),
                    "total_net_pnl_bps": total,
                    "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                    "win_rate": win_rate,
                    "fold_count": int(len(fold_totals)),
                    "positive_fold_rate": positive_fold_rate,
                    "worst_fold_net_pnl_bps": float(fold_totals.min()) if len(fold_totals) else 0.0,
                    "month_count": int(len(month_totals)),
                    "positive_month_rate": positive_month_rate,
                    "worst_month_net_pnl_bps": float(month_totals.min()) if len(month_totals) else 0.0,
                    "passed": bool(all(checks.values())),
                    "failed_checks": ";".join(name for name, passed in checks.items() if not passed),
                }
            )

    passed_rows = [row for row in rows if bool(row["passed"])]
    best = max(passed_rows, key=lambda row: (float(row["cost_bps"]), float(row["total_net_pnl_bps"]))) if passed_rows else None
    best_by_variant: dict[str, float | None] = {}
    for variant in variant_values:
        variant_passed = [row for row in passed_rows if str(row["variant"]) == variant]
        best_by_variant[f"{variant}_best_passing_cost_bps"] = max(float(row["cost_bps"]) for row in variant_passed) if variant_passed else None
    return {
        "aggregate": {
            "scenario_count": int(len(rows)),
            "passed_scenario_count": int(len(passed_rows)),
            "has_passing_cost": bool(best is not None),
            "best_passing_variant": str(best["variant"]) if best is not None else None,
            "best_passing_cost_bps": float(best["cost_bps"]) if best is not None else None,
            **best_by_variant,
        },
        "scenarios": rows,
    }


def summarize_static_bucket_viability(
    trades: pd.DataFrame,
    *,
    bucket_columns: Iterable[str],
    outcome_columns: Iterable[str] = (),
    timestamp_col: str = "timestamp",
    fold_col: str = "fold",
    pnl_col: str = "net_pnl_bps",
    min_trades: int = 50,
    min_total_net_pnl_bps: float = 0.0,
    min_positive_fold_rate: float = 1.0,
    min_positive_month_rate: float = 1.0,
    min_win_rate: float = 0.50,
) -> dict[str, object]:
    buckets = [str(col) for col in bucket_columns]
    if not buckets:
        raise ValueError("bucket_columns is empty")
    outcome_set = {str(col) for col in outcome_columns}
    required = {timestamp_col, fold_col, pnl_col, *buckets}
    missing = required.difference(trades.columns)
    if missing:
        raise ValueError(f"trades missing columns: {sorted(missing)}")
    if int(min_trades) < 1:
        raise ValueError("min_trades must be positive")

    frame = trades.copy()
    frame[timestamp_col] = pd.to_datetime(frame[timestamp_col], utc=True)
    frame[fold_col] = pd.to_numeric(frame[fold_col], errors="coerce").astype("Int64")
    frame[pnl_col] = pd.to_numeric(frame[pnl_col], errors="coerce").fillna(0.0)
    frame = frame.dropna(subset=[timestamp_col, fold_col]).copy()
    frame["month"] = frame[timestamp_col].dt.tz_convert(None).dt.to_period("M").astype(str)

    rows: list[dict[str, object]] = []
    for bucket_col in buckets:
        bucket_type = "outcome" if bucket_col in outcome_set else "pretrade"
        for value, group in frame.groupby(bucket_col, sort=True, dropna=False):
            pnl = pd.to_numeric(group[pnl_col], errors="coerce").fillna(0.0)
            fold_totals = group.assign(_pnl=pnl).groupby(fold_col, sort=True)["_pnl"].sum()
            month_totals = group.assign(_pnl=pnl).groupby("month", sort=True)["_pnl"].sum()
            total = float(pnl.sum())
            win_rate = float((pnl > 0.0).mean()) if len(pnl) else 0.0
            positive_fold_rate = float((fold_totals > 0.0).mean()) if len(fold_totals) else 0.0
            positive_month_rate = float((month_totals > 0.0).mean()) if len(month_totals) else 0.0
            checks = {
                "min_trades": int(len(group)) >= int(min_trades),
                "total_net_pnl": total >= float(min_total_net_pnl_bps),
                "positive_fold_rate": positive_fold_rate >= float(min_positive_fold_rate),
                "positive_month_rate": positive_month_rate >= float(min_positive_month_rate),
                "win_rate": win_rate >= float(min_win_rate),
            }
            rows.append(
                {
                    "bucket_column": bucket_col,
                    "bucket_value": str(value),
                    "bucket_type": bucket_type,
                    "trades": int(len(group)),
                    "total_net_pnl_bps": total,
                    "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                    "win_rate": win_rate,
                    "fold_count": int(len(fold_totals)),
                    "positive_fold_rate": positive_fold_rate,
                    "worst_fold_net_pnl_bps": float(fold_totals.min()) if len(fold_totals) else 0.0,
                    "month_count": int(len(month_totals)),
                    "positive_month_rate": positive_month_rate,
                    "worst_month_net_pnl_bps": float(month_totals.min()) if len(month_totals) else 0.0,
                    "passed": bool(all(checks.values())),
                    "failed_checks": ";".join(name for name, passed in checks.items() if not passed),
                }
            )

    rows = sorted(
        rows,
        key=lambda row: (
            str(row["bucket_type"]) == "pretrade",
            bool(row["passed"]),
            float(row["positive_fold_rate"]),
            float(row["positive_month_rate"]),
            float(row["total_net_pnl_bps"]),
        ),
        reverse=True,
    )
    passed_pretrade = [row for row in rows if row["bucket_type"] == "pretrade" and bool(row["passed"])]
    passed_outcome = [row for row in rows if row["bucket_type"] == "outcome" and bool(row["passed"])]
    return {
        "aggregate": {
            "bucket_count": int(len(rows)),
            "passed_bucket_count": int(len(passed_pretrade) + len(passed_outcome)),
            "passed_pretrade_bucket_count": int(len(passed_pretrade)),
            "passed_outcome_bucket_count": int(len(passed_outcome)),
            "promote_pretrade_bucket": bool(passed_pretrade),
            "best_pretrade_bucket": passed_pretrade[0] if passed_pretrade else None,
            "best_outcome_bucket": passed_outcome[0] if passed_outcome else None,
        },
        "buckets": rows,
    }


def summarize_rescue_hypothesis_closure(evidence: Iterable[dict[str, object]]) -> dict[str, object]:
    rows = [dict(row) for row in evidence]
    if not rows:
        raise ValueError("evidence is empty")
    normalized: list[dict[str, object]] = []
    for row in rows:
        if "hypothesis" not in row or "closed" not in row:
            raise ValueError("each evidence row must include hypothesis and closed")
        normalized.append(
            {
                **row,
                "hypothesis": str(row["hypothesis"]),
                "closed": bool(row["closed"]),
                "required": bool(row.get("required", True)),
            }
        )
    open_required = [str(row["hypothesis"]) for row in normalized if bool(row["required"]) and not bool(row["closed"])]
    closed_required = [str(row["hypothesis"]) for row in normalized if bool(row["required"]) and bool(row["closed"])]
    all_closed = len(open_required) == 0
    return {
        "hypothesis_count": int(len(normalized)),
        "required_hypothesis_count": int(sum(bool(row["required"]) for row in normalized)),
        "closed_required_hypothesis_count": int(len(closed_required)),
        "all_required_rescue_hypotheses_closed": bool(all_closed),
        "open_required_hypotheses": open_required,
        "closed_required_hypotheses": closed_required,
        "next_action": "new_hypothesis_required" if all_closed else "continue_required_rescue_validation",
        "evidence": normalized,
    }


def summarize_short_term_candidate_validation(
    trades: pd.DataFrame,
    *,
    delay_summary: pd.DataFrame,
    extra_cost_summary: pd.DataFrame,
    holdout_folds: Iterable[int],
    timestamp_col: str = "timestamp",
    fold_col: str = "fold",
    pnl_col: str = "net_pnl_bps",
    expected_lookback_minutes: int = 1440,
    expected_horizon_minutes: int = 720,
    min_trades: int = 150,
    min_total_net_pnl_bps: float = 0.0,
    min_mean_net_pnl_bps: float = 5.0,
    min_win_rate: float = 0.50,
    min_active_folds: int = 5,
    min_positive_fold_rate: float = 0.70,
    min_worst_fold_net_pnl_bps: float = -500.0,
    min_holdout_positive_fold_rate: float = 1.0,
    min_holdout_total_net_pnl_bps: float = 0.0,
    required_extra_cost_bps: float = 16.0,
    recent_months: int = 6,
    recent_tail_active_months: int = 3,
    min_recent_total_net_pnl_bps: float = 0.0,
    min_recent_active_months: int = 3,
    min_recent_active_positive_month_rate: float = 0.60,
    min_recent_tail_positive_month_rate: float = 0.67,
) -> dict[str, object]:
    required = {timestamp_col, fold_col, pnl_col, "lookback_minutes", "horizon_minutes"}
    missing = required.difference(trades.columns)
    if missing:
        raise ValueError(f"trades missing columns: {sorted(missing)}")
    if int(recent_months) < 1:
        raise ValueError("recent_months must be positive")
    if int(recent_tail_active_months) < 1:
        raise ValueError("recent_tail_active_months must be positive")

    frame = trades.copy()
    frame[timestamp_col] = pd.to_datetime(frame[timestamp_col], utc=True)
    frame[fold_col] = pd.to_numeric(frame[fold_col], errors="coerce").astype("Int64")
    frame[pnl_col] = pd.to_numeric(frame[pnl_col], errors="coerce").fillna(0.0)
    frame["lookback_minutes"] = pd.to_numeric(frame["lookback_minutes"], errors="coerce").astype("Int64")
    frame["horizon_minutes"] = pd.to_numeric(frame["horizon_minutes"], errors="coerce").astype("Int64")
    frame = frame.dropna(subset=[timestamp_col, fold_col, "lookback_minutes", "horizon_minutes"]).copy()

    pnl = pd.to_numeric(frame[pnl_col], errors="coerce").fillna(0.0)
    fold_totals = frame.assign(_pnl=pnl).groupby(fold_col, sort=True)["_pnl"].sum()
    holdout_set = {int(value) for value in holdout_folds}
    holdout_totals = fold_totals.loc[[fold for fold in fold_totals.index if int(fold) in holdout_set]]
    delay_totals = pd.to_numeric(delay_summary.get("total_net_pnl_bps", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    extra = extra_cost_summary.copy()
    extra["extra_cost_bps"] = pd.to_numeric(extra.get("extra_cost_bps", pd.Series(dtype=float)), errors="coerce")
    extra["total_net_pnl_bps"] = pd.to_numeric(extra.get("total_net_pnl_bps", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    required_extra_rows = extra.loc[extra["extra_cost_bps"] >= float(required_extra_cost_bps)]
    required_extra_total = float(required_extra_rows["total_net_pnl_bps"].max()) if len(required_extra_rows) else 0.0

    short_checks = {
        "lookback_is_24h": bool((frame["lookback_minutes"] == int(expected_lookback_minutes)).all()) if len(frame) else False,
        "horizon_is_12h": bool((frame["horizon_minutes"] == int(expected_horizon_minutes)).all()) if len(frame) else False,
        "min_trades": int(len(frame)) >= int(min_trades),
        "total_net_pnl": float(pnl.sum()) >= float(min_total_net_pnl_bps),
        "mean_net_pnl": (float(pnl.mean()) if len(pnl) else 0.0) >= float(min_mean_net_pnl_bps),
        "win_rate": (float((pnl > 0.0).mean()) if len(pnl) else 0.0) >= float(min_win_rate),
        "min_active_folds": int(len(fold_totals)) >= int(min_active_folds),
        "positive_fold_rate": (float((fold_totals > 0.0).mean()) if len(fold_totals) else 0.0) >= float(min_positive_fold_rate),
        "worst_fold_floor": (float(fold_totals.min()) if len(fold_totals) else 0.0) >= float(min_worst_fold_net_pnl_bps),
        "holdout_total_positive": (float(holdout_totals.sum()) if len(holdout_totals) else 0.0) >= float(min_holdout_total_net_pnl_bps),
        "holdout_positive_fold_rate": (float((holdout_totals > 0.0).mean()) if len(holdout_totals) else 0.0) >= float(min_holdout_positive_fold_rate),
        "delay_totals_positive": bool((delay_totals > 0.0).all()) if len(delay_totals) else False,
        "required_extra_cost_positive": required_extra_total > 0.0,
    }

    frame["month"] = frame[timestamp_col].dt.tz_convert(None).dt.to_period("M")
    month_totals = frame.groupby("month", sort=True)[pnl_col].sum()
    recent_index = pd.period_range(end=frame["month"].max(), periods=int(recent_months), freq="M") if len(frame) else pd.PeriodIndex([], freq="M")
    recent_totals = month_totals.reindex(recent_index, fill_value=0.0)
    active_recent = recent_totals.loc[recent_totals != 0.0]
    tail_active = active_recent.tail(int(recent_tail_active_months))
    recent_active_positive_rate = float((active_recent > 0.0).mean()) if len(active_recent) else 0.0
    tail_positive_rate = float((tail_active > 0.0).mean()) if len(tail_active) else 0.0
    recent_checks = {
        "recent_total_net_pnl": float(recent_totals.sum()) >= float(min_recent_total_net_pnl_bps),
        "min_recent_active_months": int(len(active_recent)) >= int(min_recent_active_months),
        "recent_active_positive_month_rate": recent_active_positive_rate >= float(min_recent_active_positive_month_rate),
        "recent_tail_active_positive_month_rate": tail_positive_rate >= float(min_recent_tail_positive_month_rate),
        "latest_active_month_positive": bool(float(active_recent.iloc[-1]) > 0.0) if len(active_recent) else False,
    }
    short_passed = bool(all(short_checks.values()))
    recent_passed = bool(all(recent_checks.values()))
    return {
        "short_term": {
            "passed": short_passed,
            "checks": short_checks,
            "failed_checks": [name for name, passed in short_checks.items() if not passed],
            "trade_count": int(len(frame)),
            "total_net_pnl_bps": float(pnl.sum()),
            "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
            "win_rate": float((pnl > 0.0).mean()) if len(pnl) else 0.0,
            "active_folds": int(len(fold_totals)),
            "positive_fold_rate": float((fold_totals > 0.0).mean()) if len(fold_totals) else 0.0,
            "worst_fold_net_pnl_bps": float(fold_totals.min()) if len(fold_totals) else 0.0,
            "holdout_total_net_pnl_bps": float(holdout_totals.sum()) if len(holdout_totals) else 0.0,
            "holdout_positive_fold_rate": float((holdout_totals > 0.0).mean()) if len(holdout_totals) else 0.0,
            "worst_delay_total_net_pnl_bps": float(delay_totals.min()) if len(delay_totals) else 0.0,
            "required_extra_cost_bps": float(required_extra_cost_bps),
            "required_extra_cost_total_net_pnl_bps": required_extra_total,
        },
        "recent": {
            "passed": recent_passed,
            "checks": recent_checks,
            "failed_checks": [name for name, passed in recent_checks.items() if not passed],
            "recent_months": int(recent_months),
            "recent_total_net_pnl_bps": float(recent_totals.sum()),
            "recent_calendar_positive_month_rate": float((recent_totals > 0.0).mean()) if len(recent_totals) else 0.0,
            "recent_active_month_count": int(len(active_recent)),
            "recent_active_positive_month_rate": recent_active_positive_rate,
            "recent_worst_month_net_pnl_bps": float(recent_totals.min()) if len(recent_totals) else 0.0,
            "tail_active_month_count": int(len(tail_active)),
            "tail_active_total_net_pnl_bps": float(tail_active.sum()) if len(tail_active) else 0.0,
            "tail_active_positive_month_rate": tail_positive_rate,
            "latest_active_month": str(active_recent.index[-1]) if len(active_recent) else None,
            "latest_active_month_net_pnl_bps": float(active_recent.iloc[-1]) if len(active_recent) else 0.0,
            "months": [
                {"month": str(month), "total_net_pnl_bps": float(total), "positive": bool(total > 0.0)}
                for month, total in recent_totals.items()
            ],
        },
        "decision": {
            "short_term_candidate_passed": short_passed,
            "recent_edge_valid": recent_passed,
            "promote_short_term_candidate": bool(short_passed and recent_passed),
            "next_action": "continue_short_term_candidate_monitoring" if short_passed and recent_passed else ("refresh_recent_data_or_wait" if short_passed else "reject_short_term_candidate"),
        },
    }


def summarize_short_term_repair_candidates(
    baseline: dict[str, object],
    candidates: Iterable[dict[str, object]],
    *,
    min_total_improvement_bps: float = 0.0,
    min_recent_total_improvement_bps: float = 0.0,
    require_holdout_not_worse: bool = True,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    baseline_short = dict(baseline.get("short_term", {}))
    baseline_recent = dict(baseline.get("recent", {}))
    base_total = float(baseline_short.get("total_net_pnl_bps", 0.0))
    base_holdout = float(baseline_short.get("holdout_total_net_pnl_bps", 0.0))
    base_recent = float(baseline_recent.get("recent_total_net_pnl_bps", 0.0))

    for raw in candidates:
        row = dict(raw)
        policy = str(row.get("policy", ""))
        if not policy:
            raise ValueError("each candidate must include policy")
        short = dict(row.get("short_term", {}))
        recent = dict(row.get("recent", {}))
        total = float(short.get("total_net_pnl_bps", 0.0))
        holdout = float(short.get("holdout_total_net_pnl_bps", 0.0))
        recent_total = float(recent.get("recent_total_net_pnl_bps", 0.0))
        total_improvement = total - base_total
        holdout_improvement = holdout - base_holdout
        recent_improvement = recent_total - base_recent
        checks = {
            "short_term_passed": bool(short.get("passed", False)),
            "recent_passed": bool(recent.get("passed", False)),
            "total_improvement": total_improvement >= float(min_total_improvement_bps),
            "recent_total_improvement": recent_improvement >= float(min_recent_total_improvement_bps),
            "holdout_not_worse": holdout_improvement >= 0.0 if bool(require_holdout_not_worse) else True,
        }
        rows.append(
            {
                "policy": policy,
                "description": str(row.get("description", "")),
                "passed": bool(all(checks.values())),
                "failed_checks": ";".join(name for name, passed in checks.items() if not passed),
                "short_term_passed": bool(short.get("passed", False)),
                "recent_passed": bool(recent.get("passed", False)),
                "trade_count": int(short.get("trade_count", 0)),
                "total_net_pnl_bps": total,
                "total_improvement_bps": total_improvement,
                "holdout_total_net_pnl_bps": holdout,
                "holdout_improvement_bps": holdout_improvement,
                "recent_total_net_pnl_bps": recent_total,
                "recent_total_improvement_bps": recent_improvement,
                "recent_tail_active_positive_month_rate": float(recent.get("tail_active_positive_month_rate", 0.0)),
                "latest_active_month": recent.get("latest_active_month"),
                "latest_active_month_net_pnl_bps": float(recent.get("latest_active_month_net_pnl_bps", 0.0)),
            }
        )

    passed = [row for row in rows if bool(row["passed"])]
    selected = (
        max(
            passed,
            key=lambda row: (
                float(row["recent_total_improvement_bps"]),
                float(row["total_improvement_bps"]),
                float(row["holdout_improvement_bps"]),
            ),
        )
        if passed
        else None
    )
    return {
        "aggregate": {
            "candidate_count": int(len(rows)),
            "passed_candidate_count": int(len(passed)),
            "promote_repair_candidate": bool(selected is not None),
            "selected_policy": str(selected["policy"]) if selected is not None else None,
            "selected_total_improvement_bps": float(selected["total_improvement_bps"]) if selected is not None else 0.0,
            "selected_recent_total_improvement_bps": float(selected["recent_total_improvement_bps"]) if selected is not None else 0.0,
            "selected_holdout_improvement_bps": float(selected["holdout_improvement_bps"]) if selected is not None else 0.0,
        },
        "candidates": rows,
    }


def summarize_two_year_stability_repair_candidates(
    baseline: dict[str, object],
    candidates: Iterable[dict[str, object]],
    *,
    min_total_improvement_bps: float = 0.0,
    min_trades: int = 100,
    require_drawdown_not_worse: bool = True,
    require_extra_cost_not_worse: bool = True,
    require_delay_not_worse: bool = True,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    baseline_aggregate = dict(baseline.get("aggregate", {}))
    base_total = float(baseline_aggregate.get("total_net_pnl_bps", 0.0))
    base_drawdown = float(baseline_aggregate.get("max_drawdown_bps", 0.0))
    base_extra_cost_total = float(baseline_aggregate.get("required_extra_cost_total_net_pnl_bps", 0.0))
    base_delay_total = float(baseline_aggregate.get("worst_delay_total_net_pnl_bps", 0.0))

    for raw in candidates:
        candidate = dict(raw)
        policy = str(candidate.get("policy", ""))
        if not policy:
            raise ValueError("each candidate must include policy")
        stability = dict(candidate.get("stability", {}))
        aggregate = dict(stability.get("aggregate", {}))
        decision = dict(stability.get("decision", {}))
        months = dict(stability.get("months", {}))
        rolling = dict(stability.get("rolling", {}))
        total = float(aggregate.get("total_net_pnl_bps", 0.0))
        drawdown = float(aggregate.get("max_drawdown_bps", 0.0))
        extra_cost_total = float(aggregate.get("required_extra_cost_total_net_pnl_bps", 0.0))
        delay_total = float(aggregate.get("worst_delay_total_net_pnl_bps", 0.0))
        total_improvement = total - base_total
        drawdown_improvement = base_drawdown - drawdown
        extra_cost_improvement = extra_cost_total - base_extra_cost_total
        delay_improvement = delay_total - base_delay_total
        checks = {
            "two_year_stable": bool(decision.get("stable_enough", False)),
            "min_trades": int(aggregate.get("trade_count", 0)) >= int(min_trades),
            "total_improvement": total_improvement >= float(min_total_improvement_bps),
            "drawdown_not_worse": drawdown_improvement >= 0.0 if bool(require_drawdown_not_worse) else True,
            "required_extra_cost_not_worse": extra_cost_improvement >= 0.0 if bool(require_extra_cost_not_worse) else True,
            "delay_not_worse": delay_improvement >= 0.0 if bool(require_delay_not_worse) else True,
        }
        rolling_3m = dict(rolling.get("rolling_3m", {}))
        rolling_6m = dict(rolling.get("rolling_6m", {}))
        rows.append(
            {
                "policy": policy,
                "description": str(candidate.get("description", "")),
                "passed": bool(all(checks.values())),
                "failed_checks": ";".join(name for name, passed in checks.items() if not passed),
                "stability_failed_checks": ";".join(str(x) for x in decision.get("failed_checks", [])),
                "trade_count": int(aggregate.get("trade_count", 0)),
                "total_net_pnl_bps": total,
                "total_improvement_bps": total_improvement,
                "mean_net_pnl_bps": float(aggregate.get("mean_net_pnl_bps", 0.0)),
                "win_rate": float(aggregate.get("win_rate", 0.0)),
                "max_drawdown_bps": drawdown,
                "drawdown_improvement_bps": drawdown_improvement,
                "required_extra_cost_total_net_pnl_bps": extra_cost_total,
                "required_extra_cost_improvement_bps": extra_cost_improvement,
                "worst_delay_total_net_pnl_bps": delay_total,
                "delay_improvement_bps": delay_improvement,
                "active_positive_month_rate": float(months.get("active_positive_month_rate", 0.0)),
                "calendar_positive_month_rate": float(months.get("calendar_positive_month_rate", 0.0)),
                "rolling_3m_positive_rate": float(rolling_3m.get("positive_rate", 0.0)),
                "rolling_6m_positive_rate": float(rolling_6m.get("positive_rate", 0.0)),
            }
        )

    passed = [row for row in rows if bool(row["passed"])]
    selected = (
        max(
            passed,
            key=lambda row: (
                float(row["total_improvement_bps"]),
                float(row["required_extra_cost_improvement_bps"]),
                float(row["delay_improvement_bps"]),
                float(row["drawdown_improvement_bps"]),
            ),
        )
        if passed
        else None
    )
    best_near = (
        max(
            rows,
            key=lambda row: (
                int(row["trade_count"]) >= int(min_trades),
                float(row["rolling_3m_positive_rate"]),
                float(row["rolling_6m_positive_rate"]),
                float(row["active_positive_month_rate"]),
                float(row["total_improvement_bps"]),
            ),
        )
        if rows
        else None
    )
    return {
        "aggregate": {
            "candidate_count": int(len(rows)),
            "passed_candidate_count": int(len(passed)),
            "promote_stability_repair": bool(selected is not None),
            "selected_policy": str(selected["policy"]) if selected is not None else None,
            "selected_total_improvement_bps": float(selected["total_improvement_bps"]) if selected is not None else 0.0,
            "selected_drawdown_improvement_bps": float(selected["drawdown_improvement_bps"]) if selected is not None else 0.0,
            "selected_required_extra_cost_improvement_bps": float(selected["required_extra_cost_improvement_bps"]) if selected is not None else 0.0,
            "selected_delay_improvement_bps": float(selected["delay_improvement_bps"]) if selected is not None else 0.0,
            "best_near_policy": str(best_near["policy"]) if best_near is not None else None,
        },
        "candidates": rows,
    }


def summarize_forward_monitoring_window(
    trades: pd.DataFrame,
    *,
    delay_summary: pd.DataFrame | None = None,
    extra_cost_summary: pd.DataFrame | None = None,
    timestamp_col: str = "timestamp",
    signal_timestamp_col: str | None = None,
    pnl_col: str = "net_pnl_bps",
    start_timestamp: str | pd.Timestamp | None = None,
    end_timestamp: str | pd.Timestamp | None = None,
    min_trades: int = 1,
    min_total_net_pnl_bps: float = 0.0,
    required_extra_cost_bps: float = 16.0,
) -> dict[str, object]:
    required = {timestamp_col, pnl_col}
    if signal_timestamp_col is not None:
        required.add(signal_timestamp_col)
    missing = required.difference(trades.columns)
    if missing:
        raise ValueError(f"trades missing columns: {sorted(missing)}")

    frame = trades.copy()
    frame[timestamp_col] = pd.to_datetime(frame[timestamp_col], utc=True)
    filter_col = signal_timestamp_col or timestamp_col
    frame[filter_col] = pd.to_datetime(frame[filter_col], utc=True)
    frame[pnl_col] = pd.to_numeric(frame[pnl_col], errors="coerce").fillna(0.0)
    frame = frame.dropna(subset=[timestamp_col, filter_col]).sort_values(timestamp_col).reset_index(drop=True)
    if start_timestamp is not None:
        start_ts = pd.to_datetime(start_timestamp, utc=True)
        frame = frame.loc[frame[filter_col] > start_ts].copy()
    else:
        start_ts = frame[filter_col].min() if len(frame) else None
    if end_timestamp is not None:
        end_ts = pd.to_datetime(end_timestamp, utc=True)
        frame = frame.loc[frame[filter_col] <= end_ts].copy()
    else:
        end_ts = frame[filter_col].max() if len(frame) else None

    pnl = pd.to_numeric(frame[pnl_col], errors="coerce").fillna(0.0)
    extra_frame = extra_cost_summary.copy() if extra_cost_summary is not None else pd.DataFrame()
    if len(extra_frame):
        extra_frame["extra_cost_bps"] = pd.to_numeric(extra_frame.get("extra_cost_bps", pd.Series(dtype=float)), errors="coerce")
        extra_frame["total_net_pnl_bps"] = pd.to_numeric(extra_frame.get("total_net_pnl_bps", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    required_extra = (
        extra_frame.loc[extra_frame.get("extra_cost_bps", pd.Series(dtype=float)) >= float(required_extra_cost_bps), "total_net_pnl_bps"]
        if len(extra_frame)
        else pd.Series(dtype=float)
    )
    required_extra_total = float(required_extra.max()) if len(required_extra) else 0.0
    delay_totals = (
        pd.to_numeric(delay_summary.get("total_net_pnl_bps", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
        if delay_summary is not None
        else pd.Series(dtype=float)
    )

    if frame.empty:
        checks = {
            "has_forward_trades": False,
            "total_net_pnl_nonnegative": True,
            "delay_totals_nonnegative": True,
            "required_extra_cost_nonnegative": True,
        }
        status = "no_signal"
        monitoring_ok = True
    else:
        checks = {
            "has_forward_trades": int(len(frame)) >= int(min_trades),
            "total_net_pnl_nonnegative": float(pnl.sum()) >= float(min_total_net_pnl_bps),
            "delay_totals_nonnegative": bool((delay_totals >= 0.0).all()) if len(delay_totals) else True,
            "required_extra_cost_nonnegative": required_extra_total >= 0.0 if len(required_extra) else True,
        }
        monitoring_ok = bool(all(checks.values()))
        status = "passed" if monitoring_ok else "failed"

    return {
        "period": {
            "start_timestamp": start_ts.isoformat() if start_ts is not None else None,
            "end_timestamp": end_ts.isoformat() if end_ts is not None else None,
            "filter_col": filter_col,
        },
        "aggregate": {
            "trade_count": int(len(frame)),
            "total_net_pnl_bps": float(pnl.sum()) if len(pnl) else 0.0,
            "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
            "win_rate": float((pnl > 0.0).mean()) if len(pnl) else 0.0,
            "worst_trade_net_pnl_bps": float(pnl.min()) if len(pnl) else 0.0,
            "best_trade_net_pnl_bps": float(pnl.max()) if len(pnl) else 0.0,
            "worst_delay_total_net_pnl_bps": float(delay_totals.min()) if len(delay_totals) else 0.0,
            "required_extra_cost_bps": float(required_extra_cost_bps),
            "required_extra_cost_total_net_pnl_bps": required_extra_total,
        },
        "decision": {
            "status": status,
            "monitoring_ok": monitoring_ok,
            "checks": checks,
            "failed_checks": [name for name, passed in checks.items() if not passed],
            "next_action": "continue_monitoring" if status == "no_signal" else ("keep_monitoring" if monitoring_ok else "investigate_forward_loss"),
        },
        "trades": frame.to_dict(orient="records"),
    }


def summarize_last_two_year_stability(
    trades: pd.DataFrame,
    *,
    delay_summary: pd.DataFrame | None = None,
    extra_cost_summary: pd.DataFrame | None = None,
    timestamp_col: str = "timestamp",
    pnl_col: str = "net_pnl_bps",
    years: int = 2,
    start_timestamp: str | pd.Timestamp | None = None,
    end_timestamp: str | pd.Timestamp | None = None,
    min_trades: int = 100,
    min_total_net_pnl_bps: float = 0.0,
    min_mean_net_pnl_bps: float = 0.0,
    min_win_rate: float = 0.50,
    min_active_month_positive_rate: float = 0.60,
    min_calendar_month_positive_rate: float = 0.40,
    min_quarter_positive_rate: float = 0.75,
    min_rolling_3m_positive_rate: float = 0.75,
    min_rolling_6m_positive_rate: float = 0.75,
    max_drawdown_bps: float = 2000.0,
    required_extra_cost_bps: float = 16.0,
) -> dict[str, object]:
    required = {timestamp_col, pnl_col}
    missing = required.difference(trades.columns)
    if missing:
        raise ValueError(f"trades missing columns: {sorted(missing)}")
    if int(years) < 1:
        raise ValueError("years must be positive")

    frame = trades.copy()
    frame[timestamp_col] = pd.to_datetime(frame[timestamp_col], utc=True)
    frame[pnl_col] = pd.to_numeric(frame[pnl_col], errors="coerce").fillna(0.0)
    frame = frame.dropna(subset=[timestamp_col]).sort_values(timestamp_col).reset_index(drop=True)
    if frame.empty:
        raise ValueError("trades is empty")

    end_ts = pd.to_datetime(end_timestamp, utc=True) if end_timestamp is not None else frame[timestamp_col].max()
    start_ts = pd.to_datetime(start_timestamp, utc=True) if start_timestamp is not None else end_ts - pd.DateOffset(years=int(years))
    scoped = frame.loc[(frame[timestamp_col] >= start_ts) & (frame[timestamp_col] <= end_ts)].copy().reset_index(drop=True)
    if scoped.empty:
        raise ValueError("no trades in requested stability window")

    pnl = pd.to_numeric(scoped[pnl_col], errors="coerce").fillna(0.0)
    equity = pnl.cumsum()
    drawdown = equity.cummax() - equity
    max_dd = float(drawdown.max()) if len(drawdown) else 0.0

    scoped["_month_period"] = scoped[timestamp_col].dt.tz_convert(None).dt.to_period("M")
    month_index = pd.period_range(start=start_ts.tz_convert(None).to_period("M"), end=end_ts.tz_convert(None).to_period("M"), freq="M")
    month_totals = scoped.groupby("_month_period", sort=True)[pnl_col].sum().reindex(month_index, fill_value=0.0)
    month_counts = scoped.groupby("_month_period", sort=True)[pnl_col].size().reindex(month_index, fill_value=0)
    active_month_totals = month_totals.loc[month_totals != 0.0]
    calendar_positive_month_rate = float((month_totals > 0.0).mean()) if len(month_totals) else 0.0
    active_positive_month_rate = float((active_month_totals > 0.0).mean()) if len(active_month_totals) else 0.0

    quarter_index = pd.period_range(start=start_ts.tz_convert(None).to_period("Q"), end=end_ts.tz_convert(None).to_period("Q"), freq="Q")
    quarter_totals = month_totals.groupby(month_totals.index.asfreq("Q")).sum().reindex(quarter_index, fill_value=0.0)
    quarter_positive_rate = float((quarter_totals > 0.0).mean()) if len(quarter_totals) else 0.0

    rolling_rows: list[dict[str, object]] = []
    rolling_summary: dict[str, dict[str, object]] = {}
    for window in (3, 6, 12):
        rolling = month_totals.rolling(window).sum().dropna()
        rows = [
            {
                "window_months": int(window),
                "end_month": str(month),
                "total_net_pnl_bps": float(total),
                "positive": bool(total > 0.0),
            }
            for month, total in rolling.items()
        ]
        rolling_rows.extend(rows)
        rolling_summary[f"rolling_{window}m"] = {
            "window_count": int(len(rolling)),
            "positive_rate": float((rolling > 0.0).mean()) if len(rolling) else 0.0,
            "worst_total_net_pnl_bps": float(rolling.min()) if len(rolling) else 0.0,
            "best_total_net_pnl_bps": float(rolling.max()) if len(rolling) else 0.0,
        }

    delay_totals = (
        pd.to_numeric(delay_summary.get("total_net_pnl_bps", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
        if delay_summary is not None
        else pd.Series(dtype=float)
    )
    extra_frame = extra_cost_summary.copy() if extra_cost_summary is not None else pd.DataFrame()
    if len(extra_frame):
        extra_frame["extra_cost_bps"] = pd.to_numeric(extra_frame.get("extra_cost_bps", pd.Series(dtype=float)), errors="coerce")
        extra_frame["total_net_pnl_bps"] = pd.to_numeric(extra_frame.get("total_net_pnl_bps", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    required_extra = extra_frame.loc[extra_frame.get("extra_cost_bps", pd.Series(dtype=float)) >= float(required_extra_cost_bps), "total_net_pnl_bps"] if len(extra_frame) else pd.Series(dtype=float)
    required_extra_total = float(required_extra.max()) if len(required_extra) else 0.0

    checks = {
        "min_trades": int(len(scoped)) >= int(min_trades),
        "total_net_pnl": float(pnl.sum()) >= float(min_total_net_pnl_bps),
        "mean_net_pnl": (float(pnl.mean()) if len(pnl) else 0.0) >= float(min_mean_net_pnl_bps),
        "win_rate": (float((pnl > 0.0).mean()) if len(pnl) else 0.0) >= float(min_win_rate),
        "active_month_positive_rate": active_positive_month_rate >= float(min_active_month_positive_rate),
        "calendar_month_positive_rate": calendar_positive_month_rate >= float(min_calendar_month_positive_rate),
        "quarter_positive_rate": quarter_positive_rate >= float(min_quarter_positive_rate),
        "rolling_3m_positive_rate": float(rolling_summary["rolling_3m"]["positive_rate"]) >= float(min_rolling_3m_positive_rate),
        "rolling_6m_positive_rate": float(rolling_summary["rolling_6m"]["positive_rate"]) >= float(min_rolling_6m_positive_rate),
        "max_drawdown": max_dd <= float(max_drawdown_bps),
        "delay_totals_positive": bool((delay_totals > 0.0).all()) if len(delay_totals) else False,
        "required_extra_cost_positive": required_extra_total > 0.0,
    }
    return {
        "period": {
            "years": int(years),
            "start_timestamp": start_ts.isoformat(),
            "end_timestamp": end_ts.isoformat(),
        },
        "aggregate": {
            "trade_count": int(len(scoped)),
            "total_net_pnl_bps": float(pnl.sum()),
            "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
            "win_rate": float((pnl > 0.0).mean()) if len(pnl) else 0.0,
            "max_drawdown_bps": max_dd,
            "worst_trade_net_pnl_bps": float(pnl.min()) if len(pnl) else 0.0,
            "best_trade_net_pnl_bps": float(pnl.max()) if len(pnl) else 0.0,
            "worst_delay_total_net_pnl_bps": float(delay_totals.min()) if len(delay_totals) else 0.0,
            "required_extra_cost_bps": float(required_extra_cost_bps),
            "required_extra_cost_total_net_pnl_bps": required_extra_total,
        },
        "months": {
            "calendar_month_count": int(len(month_totals)),
            "active_month_count": int(len(active_month_totals)),
            "calendar_positive_month_rate": calendar_positive_month_rate,
            "active_positive_month_rate": active_positive_month_rate,
            "worst_month_net_pnl_bps": float(month_totals.min()) if len(month_totals) else 0.0,
            "best_month_net_pnl_bps": float(month_totals.max()) if len(month_totals) else 0.0,
            "rows": [
                {
                    "month": str(month),
                    "trades": int(month_counts.loc[month]),
                    "total_net_pnl_bps": float(total),
                    "positive": bool(total > 0.0),
                }
                for month, total in month_totals.items()
            ],
        },
        "quarters": {
            "quarter_count": int(len(quarter_totals)),
            "positive_quarter_rate": quarter_positive_rate,
            "worst_quarter_net_pnl_bps": float(quarter_totals.min()) if len(quarter_totals) else 0.0,
            "best_quarter_net_pnl_bps": float(quarter_totals.max()) if len(quarter_totals) else 0.0,
            "rows": [
                {
                    "quarter": str(quarter),
                    "total_net_pnl_bps": float(total),
                    "positive": bool(total > 0.0),
                }
                for quarter, total in quarter_totals.items()
            ],
        },
        "rolling": {
            **rolling_summary,
            "rows": rolling_rows,
        },
        "decision": {
            "stable_enough": bool(all(checks.values())),
            "checks": checks,
            "failed_checks": [name for name, passed in checks.items() if not passed],
        },
    }


def select_design_hour_exclusion_gate(
    trades: pd.DataFrame,
    *,
    design_folds: Iterable[int],
    max_excluded_hours: int = 8,
    min_design_positive_fold_rate: float = 0.75,
    min_design_worst_fold_net_pnl_bps: float = -500.0,
) -> dict[str, object]:
    required = {"timestamp", "fold", "net_pnl_bps"}
    missing = required.difference(trades.columns)
    if missing:
        raise ValueError(f"trades missing columns: {sorted(missing)}")
    design_set = {int(x) for x in design_folds}
    if not design_set:
        raise ValueError("design_folds is empty")
    frame = trades.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["hour"] = frame["timestamp"].dt.hour.astype(int)
    frame["fold"] = pd.to_numeric(frame["fold"], errors="coerce").astype("Int64")
    frame["net_pnl_bps"] = pd.to_numeric(frame["net_pnl_bps"], errors="coerce").fillna(0.0)
    design = frame.loc[frame["fold"].astype(int).isin(design_set)].copy()
    if design.empty:
        raise ValueError("no design trades")
    hour_rank = design.groupby("hour", sort=True)["net_pnl_bps"].sum().sort_values(kind="mergesort")
    ranked_hours = [int(x) for x in hour_rank.index.tolist()]
    attempts: list[dict[str, object]] = []
    for n in range(0, min(int(max_excluded_hours), len(ranked_hours)) + 1):
        excluded = ranked_hours[:n]
        kept = design.loc[~design["hour"].isin(excluded)].copy()
        fold_totals = kept.groupby("fold", sort=True)["net_pnl_bps"].sum()
        positive_rate = float((fold_totals > 0.0).mean()) if len(fold_totals) else 0.0
        worst_fold = float(fold_totals.min()) if len(fold_totals) else 0.0
        total = float(kept["net_pnl_bps"].sum())
        passed = total > 0.0 and positive_rate >= float(min_design_positive_fold_rate) and worst_fold >= float(min_design_worst_fold_net_pnl_bps)
        row = {
            "excluded_hours": excluded,
            "selected_exclusion_count": int(n),
            "design_trades": int(len(kept)),
            "design_total_net_pnl_bps": total,
            "design_positive_fold_rate": positive_rate,
            "design_worst_fold_net_pnl_bps": worst_fold,
            "design_passed": bool(passed),
        }
        attempts.append(row)
        if passed:
            return {**row, "attempts": attempts}
    best = max(attempts, key=lambda row: (float(row["design_positive_fold_rate"]), float(row["design_total_net_pnl_bps"])))
    return {**best, "design_passed": False, "attempts": attempts}


def audit_prequential_hour_exclusion_gate(
    trades: pd.DataFrame,
    *,
    evaluation_folds: Iterable[int],
    min_history_folds: int = 4,
    max_excluded_hours: int = 8,
    min_design_positive_fold_rate: float = 0.75,
    min_design_worst_fold_net_pnl_bps: float = -500.0,
) -> dict[str, object]:
    eval_folds = [int(x) for x in evaluation_folds]
    rows: list[dict[str, object]] = []
    for fold in eval_folds:
        history_folds = sorted(int(x) for x in pd.to_numeric(trades["fold"], errors="coerce").dropna().unique() if int(x) < fold)
        if len(history_folds) < int(min_history_folds):
            rows.append(
                {
                    "fold": int(fold),
                    "risk_off": True,
                    "excluded_hours": [],
                    "trades": 0,
                    "total_net_pnl_bps": 0.0,
                    "positive": False,
                    "reason": "insufficient history",
                }
            )
            continue
        gate = select_design_hour_exclusion_gate(
            trades,
            design_folds=history_folds,
            max_excluded_hours=max_excluded_hours,
            min_design_positive_fold_rate=min_design_positive_fold_rate,
            min_design_worst_fold_net_pnl_bps=min_design_worst_fold_net_pnl_bps,
        )
        frame = trades.copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame["hour"] = frame["timestamp"].dt.hour.astype(int)
        frame["fold"] = pd.to_numeric(frame["fold"], errors="coerce").astype("Int64")
        frame["net_pnl_bps"] = pd.to_numeric(frame["net_pnl_bps"], errors="coerce").fillna(0.0)
        current = frame.loc[(frame["fold"].astype(int) == int(fold)) & (~frame["hour"].isin([int(x) for x in gate["excluded_hours"]]))].copy()
        pnl = pd.to_numeric(current["net_pnl_bps"], errors="coerce").fillna(0.0)
        total = float(pnl.sum()) if len(pnl) else 0.0
        rows.append(
            {
                "fold": int(fold),
                "risk_off": False,
                "excluded_hours": [int(x) for x in gate["excluded_hours"]],
                "trades": int(len(current)),
                "total_net_pnl_bps": total,
                "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                "win_rate": float((pnl > 0.0).mean()) if len(pnl) else 0.0,
                "positive": bool(total > 0.0),
                "reason": "selected",
            }
        )
    active = [row for row in rows if not bool(row["risk_off"])]
    active_totals = [float(row["total_net_pnl_bps"]) for row in active]
    aggregate = {
        "evaluation_folds": int(len(rows)),
        "active_folds": int(len(active)),
        "risk_off_folds": int(len(rows) - len(active)),
        "positive_active_folds": int(sum(total > 0.0 for total in active_totals)),
        "total_net_pnl_bps": float(sum(active_totals)),
        "worst_fold_net_pnl_bps": float(min(active_totals)) if active_totals else 0.0,
        "positive_fold_rate": float(np.mean([total > 0.0 for total in active_totals])) if active_totals else 0.0,
        "passed": bool(active_totals and all(total > 0.0 for total in active_totals)),
    }
    return {"aggregate": aggregate, "folds": rows}


def summarize_hour_exclusion_combination_null(
    trades: pd.DataFrame,
    *,
    selected_excluded_hours: Iterable[int],
    fold_col: str = "fold",
) -> dict[str, object]:
    required = {"timestamp", "net_pnl_bps", fold_col}
    missing = required.difference(trades.columns)
    if missing:
        raise ValueError(f"trades missing columns: {sorted(missing)}")
    selected = tuple(sorted(int(x) for x in selected_excluded_hours))
    if not selected:
        raise ValueError("selected_excluded_hours is empty")
    frame = trades.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["hour"] = frame["timestamp"].dt.hour.astype(int)
    frame["net_pnl_bps"] = pd.to_numeric(frame["net_pnl_bps"], errors="coerce").fillna(0.0)
    all_hours = tuple(range(24))
    total_pnl = float(frame["net_pnl_bps"].sum())
    hour_totals = frame.groupby("hour")["net_pnl_bps"].sum().reindex(all_hours, fill_value=0.0).to_dict()
    fold_totals = frame.groupby(fold_col)["net_pnl_bps"].sum()
    fold_hour = frame.groupby([fold_col, "hour"])["net_pnl_bps"].sum()

    selected_total = total_pnl - float(sum(hour_totals[h] for h in selected))
    selected_fold_values = []
    for fold, fold_total in fold_totals.items():
        selected_fold_values.append(float(fold_total) - float(sum(fold_hour.get((fold, h), 0.0) for h in selected)))
    selected_positive_fold_rate = float(np.mean([value > 0.0 for value in selected_fold_values])) if selected_fold_values else 0.0
    selected_worst_fold = float(min(selected_fold_values)) if selected_fold_values else 0.0

    totals: list[float] = []
    positive_rates: list[float] = []
    worst_folds: list[float] = []
    for combo in combinations(all_hours, len(selected)):
        kept_total = total_pnl - float(sum(hour_totals[h] for h in combo))
        fold_values = [float(fold_total) - float(sum(fold_hour.get((fold, h), 0.0) for h in combo)) for fold, fold_total in fold_totals.items()]
        totals.append(kept_total)
        positive_rates.append(float(np.mean([value > 0.0 for value in fold_values])) if fold_values else 0.0)
        worst_folds.append(float(min(fold_values)) if fold_values else 0.0)
    totals_arr = np.asarray(totals, dtype=float)
    positive_arr = np.asarray(positive_rates, dtype=float)
    worst_arr = np.asarray(worst_folds, dtype=float)
    return {
        "selected_excluded_hours": list(selected),
        "combination_count": int(len(totals_arr)),
        "selected_total_net_pnl_bps": float(selected_total),
        "selected_positive_fold_rate": selected_positive_fold_rate,
        "selected_worst_fold_net_pnl_bps": selected_worst_fold,
        "share_combinations_total_ge_selected": float((totals_arr >= selected_total).mean()) if len(totals_arr) else 0.0,
        "share_combinations_positive_fold_rate_ge_selected": float((positive_arr >= selected_positive_fold_rate).mean()) if len(positive_arr) else 0.0,
        "share_combinations_worst_fold_ge_selected": float((worst_arr >= selected_worst_fold).mean()) if len(worst_arr) else 0.0,
        "max_total_net_pnl_bps": float(totals_arr.max()) if len(totals_arr) else 0.0,
        "median_total_net_pnl_bps": float(np.median(totals_arr)) if len(totals_arr) else 0.0,
        "p95_total_net_pnl_bps": float(np.quantile(totals_arr, 0.95)) if len(totals_arr) else 0.0,
    }


def select_candidate_from_calibration(
    evaluations: pd.DataFrame,
    *,
    min_calibration_trades: int = 20,
    min_calibration_day_positive_rate: float = 0.5,
) -> pd.Series:
    if evaluations.empty:
        raise ValueError("evaluations is empty")
    pool = evaluations.copy()
    if "calibration_mean_net_pnl_bps" not in pool.columns:
        trades = pd.to_numeric(pool["calibration_trades"], errors="coerce").replace(0, np.nan)
        pool["calibration_mean_net_pnl_bps"] = pd.to_numeric(pool["calibration_total_net_pnl_bps"], errors="coerce") / trades
        pool["calibration_mean_net_pnl_bps"] = pool["calibration_mean_net_pnl_bps"].fillna(0.0)
    pool = pool.loc[pd.to_numeric(pool["calibration_trades"], errors="coerce").fillna(0) >= int(min_calibration_trades)]
    pool = pool.loc[pd.to_numeric(pool["calibration_day_positive_rate"], errors="coerce").fillna(0) >= float(min_calibration_day_positive_rate)]
    if pool.empty:
        raise ValueError("no candidate passed calibration requirements")
    pool = pool.sort_values(
        ["calibration_total_net_pnl_bps", "calibration_day_positive_rate", "calibration_mean_net_pnl_bps", "candidate_id"],
        ascending=[False, False, False, True],
    )
    return pool.iloc[0]


def select_candidate_by_metric_prefix(
    evaluations: pd.DataFrame,
    *,
    prefix: str,
    min_trades: int = 20,
    min_day_positive_rate: float = 0.5,
) -> pd.Series:
    if evaluations.empty:
        raise ValueError("evaluations is empty")
    metric_prefix = str(prefix)
    required = {
        "candidate_id",
        f"{metric_prefix}_trades",
        f"{metric_prefix}_total_net_pnl_bps",
        f"{metric_prefix}_day_positive_rate",
    }
    missing = required.difference(evaluations.columns)
    if missing:
        raise ValueError(f"evaluations missing required columns for {metric_prefix}: {sorted(missing)}")
    pool = evaluations.copy()
    mean_col = f"{metric_prefix}_mean_net_pnl_bps"
    if mean_col not in pool.columns:
        trades = pd.to_numeric(pool[f"{metric_prefix}_trades"], errors="coerce").replace(0, np.nan)
        pool[mean_col] = pd.to_numeric(pool[f"{metric_prefix}_total_net_pnl_bps"], errors="coerce") / trades
        pool[mean_col] = pool[mean_col].fillna(0.0)
    pool = pool.loc[pd.to_numeric(pool[f"{metric_prefix}_trades"], errors="coerce").fillna(0) >= int(min_trades)]
    pool = pool.loc[pd.to_numeric(pool[f"{metric_prefix}_day_positive_rate"], errors="coerce").fillna(0) >= float(min_day_positive_rate)]
    if pool.empty:
        raise ValueError(f"no candidate passed {metric_prefix} requirements")
    pool = pool.sort_values(
        [f"{metric_prefix}_total_net_pnl_bps", f"{metric_prefix}_day_positive_rate", mean_col, "candidate_id"],
        ascending=[False, False, False, True],
    )
    return pool.iloc[0]


def run_btcusdc_independent_validation(
    *,
    kline_paths: list[str | Path],
    out_dir: str | Path,
    calibration_end: str,
    validation_start: str,
    lookbacks: Iterable[int] = (1, 2, 3, 5, 10, 15, 30, 60, 120, 240),
    horizons: Iterable[int] = (60, 120, 240),
    directions: Iterable[str] = ("short",),
    filter_features: Iterable[str] = ("volume_ratio",),
    quantiles: Iterable[float] = (0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.92, 0.94, 0.96, 0.98),
    min_calibration_trades: int = 20,
    min_calibration_day_positive_rate: float = 0.5,
    leverage: float = 8.0,
    fee_bps: float = 8.5,
    target_account_return_pct: float = 50.0,
    clean: bool = False,
) -> dict[str, object]:
    out = Path(out_dir)
    if clean and out.exists():
        import shutil

        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    klines = load_btcusdc_klines(kline_paths)
    cal_end = pd.Timestamp(calibration_end).date().isoformat()
    val_start = pd.Timestamp(validation_start).date().isoformat()
    calibration = klines.loc[klines["replay_date"] <= cal_end].copy()
    validation = klines.loc[klines["replay_date"] >= val_start].copy()
    if calibration.empty or validation.empty:
        raise ValueError("calibration and validation splits must both be non-empty")

    candidates = candidate_grid_from_calibration(
        calibration,
        lookbacks=lookbacks,
        horizons=horizons,
        directions=directions,
        filter_features=filter_features,
        quantiles=quantiles,
        fee_bps=fee_bps,
    )
    evaluations = evaluate_candidate_grid(calibration, validation, candidates, leverage=leverage)
    selected = select_candidate_from_calibration(
        evaluations,
        min_calibration_trades=min_calibration_trades,
        min_calibration_day_positive_rate=min_calibration_day_positive_rate,
    )
    selected_candidate = BTCUSDCCandidate(
        lookback_minutes=int(selected["lookback_minutes"]),
        horizon_minutes=int(selected["horizon_minutes"]),
        direction=str(selected["direction"]),
        filter_feature=str(selected["filter_feature"]),
        threshold=float(selected["threshold"]),
        quantile=float(selected["quantile"]) if pd.notna(selected.get("quantile")) else None,
        fee_bps=float(selected["fee_bps"]),
    )
    cal_trades = build_candidate_trade_ledger(calibration, selected_candidate)
    val_trades = build_candidate_trade_ledger(validation, selected_candidate)
    cal_trades.to_csv(out / "btcusdc_v27_calibration_trades.csv", index=False)
    val_trades.to_csv(out / "btcusdc_v27_validation_trades.csv", index=False)
    evaluations.to_csv(out / "btcusdc_v27_candidate_evaluations.csv", index=False)
    _daily_metrics(cal_trades, leverage=leverage).to_csv(out / "btcusdc_v27_calibration_daily.csv", index=False)
    _daily_metrics(val_trades, leverage=leverage).to_csv(out / "btcusdc_v27_validation_daily.csv", index=False)

    validation_account_return = float(selected["validation_account_return_pct"])
    aggregate = {
        "version": "v27_btcusdc_independent_validation",
        "data_mode": "true_btcusdc_public_1m_kline_validation",
        "calibration_start": str(calibration["replay_date"].min()),
        "calibration_end": str(calibration["replay_date"].max()),
        "validation_start": str(validation["replay_date"].min()),
        "validation_end": str(validation["replay_date"].max()),
        "candidate_count": int(len(evaluations)),
        "selected_candidate_id": int(selected["candidate_id"]),
        "selected_candidate": selected_candidate.to_dict(),
        "calibration_trades": int(selected["calibration_trades"]),
        "calibration_total_net_pnl_bps": float(selected["calibration_total_net_pnl_bps"]),
        "calibration_account_return_pct": float(selected["calibration_account_return_pct"]),
        "calibration_win_rate": float(selected["calibration_win_rate"]),
        "calibration_day_positive_rate": float(selected["calibration_day_positive_rate"]),
        "validation_trades": int(selected["validation_trades"]),
        "validation_total_net_pnl_bps": float(selected["validation_total_net_pnl_bps"]),
        "validation_mean_net_pnl_bps": float(selected["validation_mean_net_pnl_bps"]),
        "validation_win_rate": float(selected["validation_win_rate"]),
        "validation_day_positive_rate": float(selected["validation_day_positive_rate"]),
        "validation_account_return_pct": validation_account_return,
        "target_account_return_pct": float(target_account_return_pct),
        "target_passed": bool(validation_account_return >= float(target_account_return_pct)),
        "selection_rule": "candidate selected only by calibration_total_net_pnl_bps, calibration_day_positive_rate, calibration_mean_net_pnl_bps",
        "caveat": "This is an independent public 1m kline validation audit, not a production L2 order-book replay or a guarantee of future profit.",
    }
    result = {"aggregate": aggregate}
    (out / "summary_v27.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    _write_report(out / "REPORT_V27.md", aggregate, selected, cal_trades, val_trades, evaluations)
    _write_report(out / "REPORT.md", aggregate, selected, cal_trades, val_trades, evaluations)
    (out / "DONE_V27.marker").write_text("ok\n", encoding="utf-8")
    return result


def run_btcusdc_rolling_forward_validation(
    *,
    kline_paths: list[str | Path],
    out_dir: str | Path,
    start_date: str,
    end_date: str,
    calibration_days: int = 20,
    validation_days: int = 10,
    step_days: int = 10,
    lookbacks: Iterable[int] = (1, 2, 3, 5, 10, 15, 30, 60, 120, 240),
    horizons: Iterable[int] = (60, 120, 240),
    directions: Iterable[str] = ("short",),
    filter_features: Iterable[str] = ("volume_ratio",),
    quantiles: Iterable[float] = (0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.92, 0.94, 0.96, 0.98),
    min_calibration_trades: int = 20,
    min_calibration_day_positive_rate: float = 0.5,
    min_calibration_account_return_pct: float | None = None,
    leverage: float = 8.0,
    fee_bps: float = 8.5,
    target_account_return_pct: float = 50.0,
    clean: bool = False,
) -> dict[str, object]:
    out = Path(out_dir)
    if clean and out.exists():
        import shutil

        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    klines = load_btcusdc_klines(kline_paths)
    windows = _rolling_windows(
        start_date=start_date,
        end_date=end_date,
        calibration_days=calibration_days,
        validation_days=validation_days,
        step_days=step_days,
    )
    if not windows:
        raise ValueError("no rolling windows created")

    fold_rows: list[dict[str, object]] = []
    candidate_rows: list[pd.DataFrame] = []
    validation_trades: list[pd.DataFrame] = []
    calibration_trades: list[pd.DataFrame] = []
    for fold, window in enumerate(windows, start=1):
        cal = klines.loc[(klines["replay_date"] >= window["calibration_start"]) & (klines["replay_date"] <= window["calibration_end"])].copy()
        val = klines.loc[(klines["replay_date"] >= window["validation_start"]) & (klines["replay_date"] <= window["validation_end"])].copy()
        if cal.empty or val.empty:
            continue
        candidates = candidate_grid_from_calibration(
            cal,
            lookbacks=lookbacks,
            horizons=horizons,
            directions=directions,
            filter_features=filter_features,
            quantiles=quantiles,
            fee_bps=fee_bps,
        )
        evaluations = evaluate_candidate_grid(cal, val, candidates, leverage=leverage)
        if evaluations.empty:
            fold_rows.append(
                {
                    "fold": int(fold),
                    **window,
                    "selected_candidate_id": -1,
                    "selected_candidate_json": "",
                    "calibration_trades": 0,
                    "calibration_total_net_pnl_bps": 0.0,
                    "calibration_account_return_pct": 0.0,
                    "calibration_win_rate": 0.0,
                    "calibration_day_positive_rate": 0.0,
                    "validation_trades": 0,
                    "validation_total_net_pnl_bps": 0.0,
                    "validation_account_return_pct": 0.0,
                    "validation_win_rate": 0.0,
                    "validation_day_positive_rate": 0.0,
                    "target_account_return_pct": float(target_account_return_pct),
                    "target_passed": False,
                    "risk_off": True,
                    "failure_reason": "no candidates generated",
                }
            )
            continue
        evaluations.insert(0, "fold", int(fold))
        candidate_rows.append(evaluations)
        try:
            selected = select_candidate_from_calibration(
                evaluations,
                min_calibration_trades=min_calibration_trades,
                min_calibration_day_positive_rate=min_calibration_day_positive_rate,
            )
        except ValueError as exc:
            fold_rows.append(
                {
                    "fold": int(fold),
                    **window,
                    "selected_candidate_id": -1,
                    "selected_candidate_json": "",
                    "calibration_trades": 0,
                    "calibration_total_net_pnl_bps": 0.0,
                    "calibration_account_return_pct": 0.0,
                    "calibration_win_rate": 0.0,
                    "calibration_day_positive_rate": 0.0,
                    "validation_trades": 0,
                    "validation_total_net_pnl_bps": 0.0,
                    "validation_account_return_pct": 0.0,
                    "validation_win_rate": 0.0,
                    "validation_day_positive_rate": 0.0,
                    "target_account_return_pct": float(target_account_return_pct),
                    "target_passed": False,
                    "risk_off": True,
                    "failure_reason": str(exc),
                }
            )
            continue
        selected_candidate = BTCUSDCCandidate(
            lookback_minutes=int(selected["lookback_minutes"]),
            horizon_minutes=int(selected["horizon_minutes"]),
            direction=str(selected["direction"]),
            filter_feature=str(selected["filter_feature"]),
            threshold=float(selected["threshold"]),
            quantile=float(selected["quantile"]) if pd.notna(selected.get("quantile")) else None,
            fee_bps=float(selected["fee_bps"]),
        )
        min_cal_return = None if min_calibration_account_return_pct is None else float(min_calibration_account_return_pct)
        if min_cal_return is not None and float(selected["calibration_account_return_pct"]) < min_cal_return:
            fold_rows.append(
                {
                    "fold": int(fold),
                    **window,
                    "selected_candidate_id": int(selected["candidate_id"]),
                    "selected_candidate_json": json.dumps(selected_candidate.to_dict(), sort_keys=True),
                    "calibration_trades": int(selected["calibration_trades"]),
                    "calibration_total_net_pnl_bps": float(selected["calibration_total_net_pnl_bps"]),
                    "calibration_account_return_pct": float(selected["calibration_account_return_pct"]),
                    "calibration_win_rate": float(selected["calibration_win_rate"]),
                    "calibration_day_positive_rate": float(selected["calibration_day_positive_rate"]),
                    "validation_trades": 0,
                    "validation_total_net_pnl_bps": 0.0,
                    "validation_account_return_pct": 0.0,
                    "validation_win_rate": 0.0,
                    "validation_day_positive_rate": 0.0,
                    "target_account_return_pct": float(target_account_return_pct),
                    "target_passed": False,
                    "risk_off": True,
                    "failure_reason": f"calibration account return below risk gate: {float(selected['calibration_account_return_pct']):.6f} < {min_cal_return:.6f}",
                }
            )
            continue
        cal_trades = build_candidate_trade_ledger(cal, selected_candidate)
        val_trades = build_candidate_trade_ledger(val, selected_candidate)
        cal_trades.insert(0, "fold", int(fold))
        val_trades.insert(0, "fold", int(fold))
        calibration_trades.append(cal_trades)
        validation_trades.append(val_trades)

        passed = float(selected["validation_account_return_pct"]) >= float(target_account_return_pct)
        fold_rows.append(
            {
                "fold": int(fold),
                **window,
                "selected_candidate_id": int(selected["candidate_id"]),
                "selected_candidate_json": json.dumps(selected_candidate.to_dict(), sort_keys=True),
                "calibration_trades": int(selected["calibration_trades"]),
                "calibration_total_net_pnl_bps": float(selected["calibration_total_net_pnl_bps"]),
                "calibration_account_return_pct": float(selected["calibration_account_return_pct"]),
                "calibration_win_rate": float(selected["calibration_win_rate"]),
                "calibration_day_positive_rate": float(selected["calibration_day_positive_rate"]),
                "validation_trades": int(selected["validation_trades"]),
                "validation_total_net_pnl_bps": float(selected["validation_total_net_pnl_bps"]),
                "validation_account_return_pct": float(selected["validation_account_return_pct"]),
                "validation_win_rate": float(selected["validation_win_rate"]),
                "validation_day_positive_rate": float(selected["validation_day_positive_rate"]),
                "target_account_return_pct": float(target_account_return_pct),
                "target_passed": bool(passed),
                "risk_off": False,
                "failure_reason": "",
            }
        )

    folds = pd.DataFrame(fold_rows)
    if folds.empty:
        raise ValueError("no fold passed calibration candidate requirements")
    all_candidates = pd.concat(candidate_rows, ignore_index=True) if candidate_rows else pd.DataFrame()
    all_calibration_trades = pd.concat(calibration_trades, ignore_index=True) if calibration_trades else pd.DataFrame()
    all_validation_trades = pd.concat(validation_trades, ignore_index=True) if validation_trades else pd.DataFrame()
    folds.to_csv(out / "btcusdc_v28_fold_metrics.csv", index=False)
    all_candidates.to_csv(out / "btcusdc_v28_candidate_evaluations.csv", index=False)
    all_calibration_trades.to_csv(out / "btcusdc_v28_calibration_trades.csv", index=False)
    all_validation_trades.to_csv(out / "btcusdc_v28_validation_trades.csv", index=False)

    passed_count = int(folds["target_passed"].astype(bool).sum())
    validation_trades_total = pd.to_numeric(folds["validation_trades"], errors="coerce").fillna(0.0)
    validation_total_pnl = pd.to_numeric(folds["validation_total_net_pnl_bps"], errors="coerce").fillna(0.0)
    validation_account = pd.to_numeric(folds["validation_account_return_pct"], errors="coerce").fillna(0.0)
    risk_off = folds["risk_off"].astype(bool) if "risk_off" in folds else pd.Series(False, index=folds.index)
    active = ~risk_off & (pd.to_numeric(folds["validation_trades"], errors="coerce").fillna(0) > 0)
    active_passed = folds.loc[active, "target_passed"].astype(bool) if active.any() else pd.Series(dtype=bool)
    aggregate = {
        "version": "v28_btcusdc_rolling_forward_validation",
        "data_mode": "true_btcusdc_public_1m_kline_rolling_forward",
        "start_date": pd.Timestamp(start_date).date().isoformat(),
        "end_date": pd.Timestamp(end_date).date().isoformat(),
        "calibration_days": int(calibration_days),
        "validation_days": int(validation_days),
        "step_days": int(step_days),
        "folds": int(len(folds)),
        "validation_windows_passed": passed_count,
        "validation_windows_failed": int(len(folds) - passed_count),
        "active_validation_windows": int(active.sum()),
        "risk_off_windows": int(risk_off.sum()),
        "active_validation_windows_passed": int(active_passed.sum()) if len(active_passed) else 0,
        "active_validation_windows_failed": int(len(active_passed) - int(active_passed.sum())) if len(active_passed) else 0,
        "all_active_validation_windows_target_passed": bool(len(active_passed) > 0 and active_passed.all()),
        "min_calibration_account_return_pct": None if min_calibration_account_return_pct is None else float(min_calibration_account_return_pct),
        "all_validation_windows_target_passed": bool(passed_count == len(folds)),
        "target_account_return_pct": float(target_account_return_pct),
        "total_validation_trades": int(validation_trades_total.sum()),
        "total_validation_net_pnl_bps": float(validation_total_pnl.sum()),
        "total_validation_account_return_pct_sum": float(validation_account.sum()),
        "min_validation_account_return_pct": float(validation_account.min()),
        "median_validation_account_return_pct": float(validation_account.median()),
        "selection_rule": "each fold selects only from its calibration window, then applies the selected candidate to the next validation window",
        "caveat": "Rolling public 1m kline validation is stronger than a single split, but still not an L2 order-book replay or a guarantee of future profit.",
    }
    result = {"aggregate": aggregate, "folds": folds.to_dict(orient="records")}
    (out / "summary_v28.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    _write_rolling_report(out / "REPORT_V28.md", aggregate, folds)
    _write_rolling_report(out / "REPORT.md", aggregate, folds)
    (out / "DONE_V28.marker").write_text("ok\n", encoding="utf-8")
    return result


def run_btcusdc_nested_recency_validation(
    *,
    kline_paths: list[str | Path],
    out_dir: str | Path,
    start_date: str,
    end_date: str,
    calibration_days: int = 20,
    selector_days: int = 10,
    validation_days: int = 10,
    step_days: int = 10,
    lookbacks: Iterable[int] = (1, 2, 3, 5, 10, 15, 30, 60, 120, 240),
    horizons: Iterable[int] = (60, 120, 240),
    directions: Iterable[str] = ("short",),
    filter_features: Iterable[str] = ("volume_ratio",),
    quantiles: Iterable[float] = (0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.92, 0.94, 0.96, 0.98),
    min_selector_trades: int = 20,
    min_selector_day_positive_rate: float = 0.5,
    leverage: float = 8.0,
    fee_bps: float = 8.5,
    target_account_return_pct: float = 50.0,
    clean: bool = False,
) -> dict[str, object]:
    if int(selector_days) <= 0 or int(selector_days) >= int(calibration_days):
        raise ValueError("selector_days must be positive and smaller than calibration_days")
    out = Path(out_dir)
    if clean and out.exists():
        import shutil

        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    klines = load_btcusdc_klines(kline_paths)
    windows = _rolling_windows(
        start_date=start_date,
        end_date=end_date,
        calibration_days=calibration_days,
        validation_days=validation_days,
        step_days=step_days,
    )
    if not windows:
        raise ValueError("no rolling windows created")

    generator_days = int(calibration_days) - int(selector_days)
    fold_rows: list[dict[str, object]] = []
    candidate_rows: list[pd.DataFrame] = []
    generator_trades: list[pd.DataFrame] = []
    selector_trades: list[pd.DataFrame] = []
    validation_trades: list[pd.DataFrame] = []
    for fold, window in enumerate(windows, start=1):
        cal_start = pd.Timestamp(window["calibration_start"]).normalize()
        generator_end = cal_start + pd.Timedelta(days=generator_days - 1)
        selector_start = generator_end + pd.Timedelta(days=1)
        selector_end = pd.Timestamp(window["calibration_end"]).normalize()
        nested_window = {
            **window,
            "generator_start": cal_start.date().isoformat(),
            "generator_end": generator_end.date().isoformat(),
            "selector_start": selector_start.date().isoformat(),
            "selector_end": selector_end.date().isoformat(),
        }
        gen = klines.loc[(klines["replay_date"] >= nested_window["generator_start"]) & (klines["replay_date"] <= nested_window["generator_end"])].copy()
        sel = klines.loc[(klines["replay_date"] >= nested_window["selector_start"]) & (klines["replay_date"] <= nested_window["selector_end"])].copy()
        val = klines.loc[(klines["replay_date"] >= window["validation_start"]) & (klines["replay_date"] <= window["validation_end"])].copy()
        if gen.empty or sel.empty or val.empty:
            continue
        candidates = candidate_grid_from_calibration(
            gen,
            lookbacks=lookbacks,
            horizons=horizons,
            directions=directions,
            filter_features=filter_features,
            quantiles=quantiles,
            fee_bps=fee_bps,
        )
        if not candidates:
            fold_rows.append(_nested_risk_off_row(fold, nested_window, target_account_return_pct, "no candidates generated"))
            continue

        selector_eval = evaluate_candidate_grid(gen, sel, candidates, leverage=leverage)
        true_eval = evaluate_candidate_grid(gen, val, candidates, leverage=leverage)
        if selector_eval.empty or true_eval.empty:
            fold_rows.append(_nested_risk_off_row(fold, nested_window, target_account_return_pct, "no candidates evaluated"))
            continue
        selector_metrics = selector_eval[["candidate_id", *[c for c in selector_eval.columns if c.startswith("validation_")]]].rename(
            columns={c: c.replace("validation_", "selector_", 1) for c in selector_eval.columns if c.startswith("validation_")}
        )
        generator_metrics = true_eval[["candidate_id", *[c for c in true_eval.columns if c.startswith("calibration_")]]].rename(
            columns={c: c.replace("calibration_", "generator_", 1) for c in true_eval.columns if c.startswith("calibration_")}
        )
        candidate_base_cols = [
            "candidate_id",
            "lookback_minutes",
            "horizon_minutes",
            "direction",
            "filter_feature",
            "threshold",
            "fee_bps",
            "quantile",
            "candidate_json",
            *[c for c in true_eval.columns if c.startswith("validation_")],
        ]
        evaluations = true_eval[candidate_base_cols].merge(generator_metrics, on="candidate_id", how="left").merge(selector_metrics, on="candidate_id", how="left")
        evaluations.insert(0, "fold", int(fold))
        candidate_rows.append(evaluations)

        try:
            selected = select_candidate_by_metric_prefix(
                evaluations,
                prefix="selector",
                min_trades=min_selector_trades,
                min_day_positive_rate=min_selector_day_positive_rate,
            )
        except ValueError as exc:
            fold_rows.append(_nested_risk_off_row(fold, nested_window, target_account_return_pct, str(exc)))
            continue

        selected_candidate = BTCUSDCCandidate(
            lookback_minutes=int(selected["lookback_minutes"]),
            horizon_minutes=int(selected["horizon_minutes"]),
            direction=str(selected["direction"]),
            filter_feature=str(selected["filter_feature"]),
            threshold=float(selected["threshold"]),
            quantile=float(selected["quantile"]) if pd.notna(selected.get("quantile")) else None,
            fee_bps=float(selected["fee_bps"]),
        )
        gen_trades = build_candidate_trade_ledger(gen, selected_candidate)
        sel_trades = build_candidate_trade_ledger(sel, selected_candidate)
        val_trades = build_candidate_trade_ledger(val, selected_candidate)
        gen_trades.insert(0, "fold", int(fold))
        sel_trades.insert(0, "fold", int(fold))
        val_trades.insert(0, "fold", int(fold))
        generator_trades.append(gen_trades)
        selector_trades.append(sel_trades)
        validation_trades.append(val_trades)

        validation_return = float(selected["validation_account_return_pct"])
        fold_rows.append(
            {
                "fold": int(fold),
                **nested_window,
                "selected_candidate_id": int(selected["candidate_id"]),
                "selected_candidate_json": json.dumps(selected_candidate.to_dict(), sort_keys=True),
                "generator_trades": int(selected["generator_trades"]),
                "generator_total_net_pnl_bps": float(selected["generator_total_net_pnl_bps"]),
                "generator_account_return_pct": float(selected["generator_account_return_pct"]),
                "generator_win_rate": float(selected["generator_win_rate"]),
                "generator_day_positive_rate": float(selected["generator_day_positive_rate"]),
                "selector_trades": int(selected["selector_trades"]),
                "selector_total_net_pnl_bps": float(selected["selector_total_net_pnl_bps"]),
                "selector_account_return_pct": float(selected["selector_account_return_pct"]),
                "selector_win_rate": float(selected["selector_win_rate"]),
                "selector_day_positive_rate": float(selected["selector_day_positive_rate"]),
                "validation_trades": int(selected["validation_trades"]),
                "validation_total_net_pnl_bps": float(selected["validation_total_net_pnl_bps"]),
                "validation_account_return_pct": validation_return,
                "validation_win_rate": float(selected["validation_win_rate"]),
                "validation_day_positive_rate": float(selected["validation_day_positive_rate"]),
                "target_account_return_pct": float(target_account_return_pct),
                "target_passed": bool(validation_return >= float(target_account_return_pct)),
                "risk_off": False,
                "failure_reason": "",
            }
        )

    folds = pd.DataFrame(fold_rows)
    if folds.empty:
        raise ValueError("no nested recency folds produced")
    all_candidates = pd.concat(candidate_rows, ignore_index=True) if candidate_rows else pd.DataFrame()
    all_generator_trades = pd.concat(generator_trades, ignore_index=True) if generator_trades else pd.DataFrame()
    all_selector_trades = pd.concat(selector_trades, ignore_index=True) if selector_trades else pd.DataFrame()
    all_validation_trades = pd.concat(validation_trades, ignore_index=True) if validation_trades else pd.DataFrame()
    folds.to_csv(out / "btcusdc_v43_fold_metrics.csv", index=False)
    all_candidates.to_csv(out / "btcusdc_v43_candidate_evaluations.csv", index=False)
    all_generator_trades.to_csv(out / "btcusdc_v43_generator_trades.csv", index=False)
    all_selector_trades.to_csv(out / "btcusdc_v43_selector_trades.csv", index=False)
    all_validation_trades.to_csv(out / "btcusdc_v43_validation_trades.csv", index=False)

    risk_off = folds["risk_off"].astype(bool) if "risk_off" in folds else pd.Series(False, index=folds.index)
    active = ~risk_off & (pd.to_numeric(folds["validation_trades"], errors="coerce").fillna(0) > 0)
    validation_values = pd.to_numeric(folds["validation_account_return_pct"], errors="coerce").fillna(0.0)
    active_values = validation_values.loc[active]
    target_passed = validation_values >= float(target_account_return_pct)
    active_passed = active_values >= float(target_account_return_pct)
    aggregate = {
        "version": "v43_btcusdc_nested_recency_validation",
        "data_mode": "true_btcusdc_public_aggtrade_1m_flow_nested_recency",
        "start_date": pd.Timestamp(start_date).date().isoformat(),
        "end_date": pd.Timestamp(end_date).date().isoformat(),
        "calibration_days": int(calibration_days),
        "generator_days": int(generator_days),
        "selector_days": int(selector_days),
        "validation_days": int(validation_days),
        "step_days": int(step_days),
        "folds": int(len(folds)),
        "candidate_evaluations": int(len(all_candidates)),
        "validation_windows_passed": int(target_passed.sum()),
        "validation_windows_failed": int(len(folds) - int(target_passed.sum())),
        "active_validation_windows": int(active.sum()),
        "risk_off_windows": int(risk_off.sum()),
        "active_validation_windows_passed": int(active_passed.sum()) if len(active_passed) else 0,
        "active_validation_windows_failed": int(len(active_passed) - int(active_passed.sum())) if len(active_passed) else 0,
        "all_active_validation_windows_target_passed": bool(len(active_passed) > 0 and active_passed.all()),
        "target_account_return_pct": float(target_account_return_pct),
        "total_validation_trades": int(pd.to_numeric(folds["validation_trades"], errors="coerce").fillna(0).sum()),
        "total_validation_net_pnl_bps": float(pd.to_numeric(folds["validation_total_net_pnl_bps"], errors="coerce").fillna(0.0).sum()),
        "total_validation_account_return_pct_sum": float(validation_values.sum()),
        "min_validation_account_return_pct": float(validation_values.min()) if len(validation_values) else 0.0,
        "median_validation_account_return_pct": float(validation_values.median()) if len(validation_values) else 0.0,
        "selection_rule": "within each rolling window, generate candidates on the early calibration slice, select by the later calibration selector slice, then apply the selected candidate to forward validation",
        "caveat": "Nested recency validation prevents direct validation leakage, but it is still not an L2 order-book replay or a guarantee of future profit.",
    }
    result = {"aggregate": aggregate, "folds": folds.to_dict(orient="records")}
    (out / "summary_v43.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    _write_nested_report(out / "REPORT_V43.md", aggregate, folds)
    _write_nested_report(out / "REPORT.md", aggregate, folds)
    (out / "DONE_V43.marker").write_text("ok\n", encoding="utf-8")
    return result


def audit_candidate_selection_gap(
    evaluations: pd.DataFrame,
    *,
    target_account_return_pct: float = 50.0,
    selector_score: str = "calibration_account_return_pct",
    min_calibration_trades: int = 20,
    min_calibration_day_positive_rate: float = 0.5,
) -> dict[str, object]:
    if evaluations.empty:
        raise ValueError("evaluations is empty")
    rows: list[dict[str, object]] = []
    for fold, grp in evaluations.groupby("fold", sort=True):
        oracle = grp.sort_values(["validation_account_return_pct", "candidate_id"], ascending=[False, True]).iloc[0]
        pool = grp.loc[
            (pd.to_numeric(grp["calibration_trades"], errors="coerce").fillna(0) >= int(min_calibration_trades))
            & (pd.to_numeric(grp["calibration_day_positive_rate"], errors="coerce").fillna(0) >= float(min_calibration_day_positive_rate))
        ].copy()
        selector = None if pool.empty else pool.sort_values([selector_score, "candidate_id"], ascending=[False, True]).iloc[0]
        selector_val = 0.0 if selector is None else float(selector["validation_account_return_pct"])
        rows.append(
            {
                "fold": int(fold),
                "oracle_candidate_id": int(oracle["candidate_id"]),
                "oracle_validation_account_return_pct": float(oracle["validation_account_return_pct"]),
                "oracle_target_passed": bool(float(oracle["validation_account_return_pct"]) >= float(target_account_return_pct)),
                "selector_candidate_id": -1 if selector is None else int(selector["candidate_id"]),
                "selector_validation_account_return_pct": selector_val,
                "selector_target_passed": bool(selector_val >= float(target_account_return_pct)),
                "selector_risk_off": selector is None,
                "selector_score": str(selector_score),
            }
        )
    folds = pd.DataFrame(rows)
    oracle_passed = int(folds["oracle_target_passed"].astype(bool).sum())
    selector_passed = int(folds["selector_target_passed"].astype(bool).sum())
    aggregate = {
        "folds": int(len(folds)),
        "target_account_return_pct": float(target_account_return_pct),
        "oracle_windows_passed": oracle_passed,
        "oracle_windows_failed": int(len(folds) - oracle_passed),
        "calibration_selector_windows_passed": selector_passed,
        "calibration_selector_windows_failed": int(len(folds) - selector_passed),
        "oracle_minus_selector_pass_gap": int(oracle_passed - selector_passed),
        "oracle_total_validation_account_return_pct": float(folds["oracle_validation_account_return_pct"].sum()),
        "selector_total_validation_account_return_pct": float(folds["selector_validation_account_return_pct"].sum()),
        "selector_score": str(selector_score),
    }
    return {"aggregate": aggregate, "folds": folds.to_dict(orient="records")}


def audit_prequential_selector_policies(
    evaluations: pd.DataFrame,
    *,
    policy_scores: Iterable[str] = (
        "calibration_account_return_pct",
        "calibration_mean_net_pnl_bps",
        "calibration_win_rate",
        "calibration_day_positive_rate",
        "calibration_min_day_net_pnl_bps",
        "score_return_x_day",
        "score_mean_sqrt_trades",
    ),
    direction_filters: Iterable[str] = ("*", "momentum", "reversal", "long", "short"),
    filter_feature_filters: Iterable[str] = ("*", "volume_ratio", "abs_return_bps", "range_bps"),
    quantile_max_values: Iterable[float] = (0.8, 0.9, 0.98),
    min_calibration_trades: int = 20,
    min_calibration_day_positive_rate: float = 0.5,
    warmup_folds: int = 2,
    ranking_rule: str = "prior_pass_total",
    target_account_return_pct: float = 50.0,
) -> dict[str, object]:
    if evaluations.empty:
        raise ValueError("evaluations is empty")
    frame = evaluations.copy()
    frame = _add_selector_policy_scores(frame)
    policy_results = _evaluate_selector_policy_grid(
        frame,
        policy_scores=policy_scores,
        direction_filters=direction_filters,
        filter_feature_filters=filter_feature_filters,
        quantile_max_values=quantile_max_values,
        min_calibration_trades=min_calibration_trades,
        min_calibration_day_positive_rate=min_calibration_day_positive_rate,
    )
    if policy_results.empty:
        raise ValueError("no selector policies evaluated")

    selected_rows: list[dict[str, object]] = []
    fold_values = sorted(int(x) for x in frame["fold"].dropna().unique())
    for fold in fold_values:
        if fold <= int(warmup_folds):
            selected_rows.append(
                {
                    "fold": int(fold),
                    "policy_id": -1,
                    "candidate_id": -1,
                    "validation_account_return_pct": 0.0,
                    "target_passed": False,
                    "risk_off": True,
                    "reason": "warmup",
                }
            )
            continue
        history = policy_results.loc[policy_results["fold"] < fold].copy()
        current = policy_results.loc[policy_results["fold"] == fold].copy()
        policy_rank = _rank_selector_policies(history, ranking_rule=ranking_rule, target_account_return_pct=target_account_return_pct)
        if policy_rank.empty:
            selected_rows.append(
                {
                    "fold": int(fold),
                    "policy_id": -1,
                    "candidate_id": -1,
                    "validation_account_return_pct": 0.0,
                    "target_passed": False,
                    "risk_off": True,
                    "reason": "no policy history",
                }
            )
            continue
        chosen = policy_rank.iloc[0]
        current_policy = current.loc[current["policy_id"] == int(chosen["policy_id"])]
        if current_policy.empty:
            raise ValueError(f"missing current policy row for fold={fold} policy_id={int(chosen['policy_id'])}")
        row = current_policy.iloc[0].to_dict()
        row["rank_score"] = float(chosen["rank_score"])
        row["target_passed"] = bool(float(row["validation_account_return_pct"]) >= float(target_account_return_pct))
        row["reason"] = "selected"
        selected_rows.append(row)

    folds = pd.DataFrame(selected_rows)
    values = pd.to_numeric(folds["validation_account_return_pct"], errors="coerce").fillna(0.0)
    risk_off = folds["risk_off"].astype(bool)
    static = _summarize_selector_policies(policy_results, target_account_return_pct=target_account_return_pct)
    aggregate = {
        "version": "v31_btcusdc_prequential_selector_policy_audit",
        "folds": int(len(folds)),
        "warmup_folds": int(warmup_folds),
        "ranking_rule": str(ranking_rule),
        "target_account_return_pct": float(target_account_return_pct),
        "policy_count": int(policy_results["policy_id"].nunique()),
        "prequential_active_windows": int((~risk_off).sum()),
        "prequential_risk_off_windows": int(risk_off.sum()),
        "prequential_windows_passed": int((values >= float(target_account_return_pct)).sum()),
        "prequential_windows_failed": int((~risk_off).sum() - int((values >= float(target_account_return_pct)).sum())),
        "prequential_total_validation_account_return_pct": float(values.sum()),
        "prequential_min_validation_account_return_pct": float(values.min()) if len(values) else 0.0,
        "prequential_median_validation_account_return_pct": float(values.median()) if len(values) else 0.0,
        "best_static_policy_passed_windows": int(static.iloc[0]["passed_windows"]) if not static.empty else 0,
        "best_static_policy_total_validation_account_return_pct": float(static.iloc[0]["total_validation_account_return_pct"]) if not static.empty else 0.0,
        "selection_rule": "each fold after warmup chooses a selector policy using only earlier completed fold outcomes",
        "caveat": "This audits selector stability on public 1m klines; it is not a production L2 replay or a guarantee of future profit.",
    }
    return {
        "aggregate": aggregate,
        "folds": folds.to_dict(orient="records"),
        "policy_results": policy_results.to_dict(orient="records"),
        "static_policy_summary": static.to_dict(orient="records"),
    }


def audit_prequential_meta_selector(
    evaluations: pd.DataFrame,
    *,
    feature_columns: Iterable[str] = (
        "lookback_minutes",
        "horizon_minutes",
        "direction",
        "filter_feature",
        "quantile",
        "threshold",
        "generator_trades",
        "generator_account_return_pct",
        "generator_day_positive_rate",
        "generator_min_day_net_pnl_bps",
        "selector_trades",
        "selector_account_return_pct",
        "selector_day_positive_rate",
        "selector_min_day_net_pnl_bps",
    ),
    warmup_folds: int = 2,
    min_selector_trades: int = 20,
    min_selector_day_positive_rate: float = 0.0,
    model_type: str = "random_forest",
    target_account_return_pct: float = 50.0,
) -> dict[str, object]:
    if evaluations.empty:
        raise ValueError("evaluations is empty")
    features = tuple(str(c) for c in feature_columns)
    required = {"fold", "candidate_id", "validation_account_return_pct", "selector_trades", "selector_day_positive_rate", *features}
    missing = required.difference(evaluations.columns)
    if missing:
        raise ValueError(f"evaluations missing columns: {sorted(missing)}")

    frame = evaluations.copy()
    fold_values = sorted(int(x) for x in frame["fold"].dropna().unique())
    rows: list[dict[str, object]] = []
    for fold in fold_values:
        if fold <= int(warmup_folds):
            rows.append(_meta_selector_risk_off_row(fold, model_type, "warmup"))
            continue
        history = frame.loc[frame["fold"] < fold].copy()
        current = frame.loc[
            (frame["fold"] == fold)
            & (pd.to_numeric(frame["selector_trades"], errors="coerce").fillna(0) >= int(min_selector_trades))
            & (pd.to_numeric(frame["selector_day_positive_rate"], errors="coerce").fillna(0) >= float(min_selector_day_positive_rate))
        ].copy()
        if history.empty or current.empty:
            rows.append(_meta_selector_risk_off_row(fold, model_type, "missing history or current candidates"))
            continue
        model = _make_meta_selector_model(model_type, history, features)
        history_x = history.loc[:, features].replace([np.inf, -np.inf], np.nan)
        current_x = current.loc[:, features].replace([np.inf, -np.inf], np.nan)
        model.fit(history_x, pd.to_numeric(history["validation_account_return_pct"], errors="coerce").fillna(0.0))
        current["predicted_validation_account_return_pct"] = model.predict(current_x)
        selected = current.sort_values(["predicted_validation_account_return_pct", "candidate_id"], ascending=[False, True]).iloc[0]
        value = float(selected["validation_account_return_pct"])
        row = {
            "fold": int(fold),
            "model_type": str(model_type),
            "candidate_id": int(selected["candidate_id"]),
            "predicted_validation_account_return_pct": float(selected["predicted_validation_account_return_pct"]),
            "validation_account_return_pct": value,
            "target_passed": bool(value >= float(target_account_return_pct)),
            "risk_off": False,
            "reason": "selected",
        }
        for col in ("lookback_minutes", "horizon_minutes", "direction", "filter_feature", "quantile", "threshold"):
            if col in selected.index:
                row[col] = selected[col]
        rows.append(row)

    folds = pd.DataFrame(rows)
    values = pd.to_numeric(folds["validation_account_return_pct"], errors="coerce").fillna(0.0)
    risk_off = folds["risk_off"].astype(bool)
    active = ~risk_off
    active_values = values.loc[active]
    active_passed = active_values >= float(target_account_return_pct)
    aggregate = {
        "version": "v44_btcusdc_prequential_meta_selector_audit",
        "folds": int(len(folds)),
        "warmup_folds": int(warmup_folds),
        "model_type": str(model_type),
        "feature_columns": list(features),
        "target_account_return_pct": float(target_account_return_pct),
        "prequential_active_windows": int(active.sum()),
        "prequential_risk_off_windows": int(risk_off.sum()),
        "prequential_windows_passed": int(active_passed.sum()) if len(active_passed) else 0,
        "prequential_windows_failed": int(len(active_passed) - int(active_passed.sum())) if len(active_passed) else 0,
        "prequential_total_validation_account_return_pct": float(active_values.sum()) if len(active_values) else 0.0,
        "prequential_min_validation_account_return_pct": float(active_values.min()) if len(active_values) else 0.0,
        "prequential_median_validation_account_return_pct": float(active_values.median()) if len(active_values) else 0.0,
        "all_active_validation_windows_target_passed": bool(len(active_passed) > 0 and active_passed.all()),
        "selection_rule": "train a candidate-level meta model on completed folds only, then select the current candidate with the highest predicted validation account return",
        "caveat": "This is a prequential selector audit, not a production L2 replay or a guarantee of future profit.",
    }
    return {"aggregate": aggregate, "folds": folds.to_dict(orient="records")}


def audit_fixed_family_transfer(
    evaluations: pd.DataFrame,
    *,
    group_columns: Iterable[str] = ("horizon_minutes", "direction", "filter_feature", "quantile"),
    train_folds: Iterable[int],
    validation_folds: Iterable[int],
    current_selection_score: str = "selector_account_return_pct",
    target_account_return_pct: float = 50.0,
    min_current_trades: int = 0,
    current_trades_column: str = "selector_trades",
) -> dict[str, object]:
    if evaluations.empty:
        raise ValueError("evaluations is empty")
    groups = tuple(str(x) for x in group_columns)
    required = {"fold", "candidate_id", "validation_account_return_pct", current_selection_score, *groups}
    missing = required.difference(evaluations.columns)
    if missing:
        raise ValueError(f"evaluations missing columns: {sorted(missing)}")
    frame = evaluations.copy()
    if current_trades_column in frame.columns:
        frame = frame.loc[pd.to_numeric(frame[current_trades_column], errors="coerce").fillna(0) >= int(min_current_trades)].copy()
    family_outcomes = _family_fold_outcomes(frame, groups, current_selection_score=current_selection_score)
    train_set = {int(x) for x in train_folds}
    validation_set = {int(x) for x in validation_folds}
    train = family_outcomes.loc[family_outcomes["fold"].astype(int).isin(train_set)].copy()
    validation = family_outcomes.loc[family_outcomes["fold"].astype(int).isin(validation_set)].copy()
    if train.empty:
        raise ValueError("no train family outcomes")
    if validation.empty:
        raise ValueError("no validation family outcomes")

    train_summary = _summarize_candidate_families(train, groups, target_account_return_pct=target_account_return_pct)
    if train_summary.empty:
        raise ValueError("no train families summarized")
    selected_family = train_summary.iloc[0]
    selected_validation = _filter_family(validation, selected_family, groups).sort_values("fold").reset_index(drop=True)
    values = pd.to_numeric(selected_validation["validation_account_return_pct"], errors="coerce").fillna(0.0)
    passed = values >= float(target_account_return_pct)
    selected_family_dict = {col: _json_scalar(selected_family[col]) for col in groups}
    aggregate = {
        "version": "v46_btcusdc_fixed_family_transfer_audit",
        "group_columns": list(groups),
        "train_folds": sorted(train_set),
        "validation_folds": sorted(validation_set),
        "current_selection_score": str(current_selection_score),
        "target_account_return_pct": float(target_account_return_pct),
        "selected_family": selected_family_dict,
        "train_windows": int(selected_family["observed_folds"]),
        "train_windows_passed": int(selected_family["passed_windows"]),
        "train_total_account_return_pct": float(selected_family["total_validation_account_return_pct"]),
        "train_min_account_return_pct": float(selected_family["min_validation_account_return_pct"]),
        "validation_windows": int(len(selected_validation)),
        "validation_windows_passed": int(passed.sum()),
        "validation_windows_failed": int(len(selected_validation) - int(passed.sum())),
        "validation_total_account_return_pct": float(values.sum()) if len(values) else 0.0,
        "validation_min_account_return_pct": float(values.min()) if len(values) else 0.0,
        "validation_median_account_return_pct": float(values.median()) if len(values) else 0.0,
        "all_validation_windows_target_passed": bool(len(passed) > 0 and passed.all()),
        "selection_rule": "select the fixed family using train folds only, then evaluate the same family on held-out validation folds",
        "caveat": "This audits family transfer across historical folds; it is not a production L2 replay or a guarantee of future profit.",
    }
    return {
        "aggregate": aggregate,
        "train_family_summary": train_summary.to_dict(orient="records"),
        "validation_folds": selected_validation.to_dict(orient="records"),
    }


def audit_hourly_gate_transfer(
    selector_trades: pd.DataFrame,
    validation_trades: pd.DataFrame,
    *,
    top_n_values: Iterable[int] = (1, 2, 3, 4, 6, 8, 12, 16, 24),
    leverage: float = 8.0,
    target_account_return_pct: float = 50.0,
) -> dict[str, object]:
    if selector_trades.empty:
        raise ValueError("selector_trades is empty")
    if validation_trades.empty:
        raise ValueError("validation_trades is empty")
    required = {"fold", "timestamp", "net_pnl_bps"}
    missing_selector = required.difference(selector_trades.columns)
    missing_validation = required.difference(validation_trades.columns)
    if missing_selector:
        raise ValueError(f"selector_trades missing columns: {sorted(missing_selector)}")
    if missing_validation:
        raise ValueError(f"validation_trades missing columns: {sorted(missing_validation)}")

    selector = selector_trades.copy()
    validation = validation_trades.copy()
    selector["timestamp"] = pd.to_datetime(selector["timestamp"], utc=True)
    validation["timestamp"] = pd.to_datetime(validation["timestamp"], utc=True)
    selector["hour"] = selector["timestamp"].dt.hour.astype(int)
    validation["hour"] = validation["timestamp"].dt.hour.astype(int)

    rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    fold_values = sorted(int(x) for x in selector["fold"].dropna().unique())
    for top_n in top_n_values:
        top_n_int = int(top_n)
        for fold in fold_values:
            sel_fold = selector.loc[selector["fold"].astype(int) == fold].copy()
            val_fold = validation.loc[validation["fold"].astype(int) == fold].copy()
            if sel_fold.empty or val_fold.empty:
                rows.append(_hourly_gate_row(fold, top_n_int, [], 0, 0.0, leverage, target_account_return_pct, risk_off=True))
                continue
            hourly = (
                sel_fold.groupby("hour", sort=True)
                .agg(selector_total_net_pnl_bps=("net_pnl_bps", "sum"), selector_mean_net_pnl_bps=("net_pnl_bps", "mean"), selector_trades=("net_pnl_bps", "size"))
                .reset_index()
                .sort_values(["selector_total_net_pnl_bps", "selector_mean_net_pnl_bps", "hour"], ascending=[False, False, True])
            )
            hours = [int(x) for x in hourly.head(top_n_int)["hour"].tolist()]
            gated = val_fold.loc[val_fold["hour"].isin(hours)].copy()
            pnl = float(pd.to_numeric(gated["net_pnl_bps"], errors="coerce").fillna(0.0).sum()) if not gated.empty else 0.0
            rows.append(_hourly_gate_row(fold, top_n_int, hours, int(len(gated)), pnl, leverage, target_account_return_pct, risk_off=False))
        top_rows = [r for r in rows if int(r["top_n_hours"]) == top_n_int]
        values = pd.Series([float(r["validation_account_return_pct"]) for r in top_rows], dtype=float)
        risk_off = pd.Series([bool(r["risk_off"]) for r in top_rows], dtype=bool)
        active_values = values.loc[~risk_off]
        passed = active_values >= float(target_account_return_pct)
        summary_rows.append(
            {
                "top_n_hours": top_n_int,
                "folds": int(len(top_rows)),
                "active_windows": int((~risk_off).sum()),
                "risk_off_windows": int(risk_off.sum()),
                "validation_windows_passed": int(passed.sum()) if len(passed) else 0,
                "validation_windows_failed": int(len(passed) - int(passed.sum())) if len(passed) else 0,
                "validation_total_account_return_pct": float(active_values.sum()) if len(active_values) else 0.0,
                "validation_min_account_return_pct": float(active_values.min()) if len(active_values) else 0.0,
                "validation_median_account_return_pct": float(active_values.median()) if len(active_values) else 0.0,
                "total_validation_trades": int(sum(int(r["validation_trades"]) for r in top_rows)),
                "all_active_validation_windows_target_passed": bool(len(passed) > 0 and passed.all()),
            }
        )
    summary = pd.DataFrame(summary_rows).sort_values(
        ["validation_windows_passed", "validation_total_account_return_pct", "validation_min_account_return_pct"],
        ascending=[False, False, False],
    )
    aggregate = {
        "version": "v47_btcusdc_hourly_gate_transfer_audit",
        "target_account_return_pct": float(target_account_return_pct),
        "best": summary.iloc[0].to_dict() if not summary.empty else {},
        "selection_rule": "within each fold, rank hours by selector-window PnL only, then keep validation trades from the selected hours",
        "caveat": "This audits hour-of-day transfer for selected candidates; it is not a production L2 replay or a guarantee of future profit.",
    }
    return {"aggregate": aggregate, "folds": rows, "summary": summary.to_dict(orient="records")}


def audit_prequential_family_selector(
    evaluations: pd.DataFrame,
    *,
    group_columns: Iterable[str] = ("horizon_minutes", "direction", "filter_feature", "quantile"),
    warmup_folds: int = 2,
    ranking_rule: str = "prior_pass_total",
    current_selection_score: str = "calibration_min_day_net_pnl_bps",
    target_account_return_pct: float = 50.0,
    min_calibration_trades: int = 20,
    min_calibration_day_positive_rate: float = 0.0,
) -> dict[str, object]:
    if evaluations.empty:
        raise ValueError("evaluations is empty")
    frame = evaluations.copy()
    groups = tuple(str(x) for x in group_columns)
    missing = set(groups).difference(frame.columns)
    if missing:
        raise ValueError(f"missing group columns: {sorted(missing)}")
    if current_selection_score not in frame.columns:
        raise ValueError(f"unknown current_selection_score: {current_selection_score}")
    eligible = frame.loc[
        (pd.to_numeric(frame["calibration_trades"], errors="coerce").fillna(0) >= int(min_calibration_trades))
        & (pd.to_numeric(frame["calibration_day_positive_rate"], errors="coerce").fillna(0) >= float(min_calibration_day_positive_rate))
    ].copy()
    family_outcomes = _family_fold_outcomes(eligible, groups, current_selection_score=current_selection_score)

    rows: list[dict[str, object]] = []
    fold_values = sorted(int(x) for x in frame["fold"].dropna().unique())
    for fold in fold_values:
        if fold <= int(warmup_folds):
            rows.append(
                {
                    "fold": int(fold),
                    "candidate_id": -1,
                    "validation_account_return_pct": 0.0,
                    "target_passed": False,
                    "risk_off": True,
                    "reason": "warmup",
                }
            )
            continue
        history = family_outcomes.loc[family_outcomes["fold"] < fold].copy()
        current = family_outcomes.loc[family_outcomes["fold"] == fold].copy()
        if history.empty or current.empty:
            rows.append(
                {
                    "fold": int(fold),
                    "candidate_id": -1,
                    "validation_account_return_pct": 0.0,
                    "target_passed": False,
                    "risk_off": True,
                    "reason": "missing history or current fold",
                }
            )
            continue
        rank = _rank_candidate_families(history, groups, ranking_rule=ranking_rule, target_account_return_pct=target_account_return_pct)
        selected = None
        selected_family = None
        for _, family in rank.iterrows():
            pool = _filter_family(current, family, groups)
            if pool.empty:
                continue
            selected = pool.iloc[0]
            selected_family = family
            break
        if selected is None:
            rows.append(
                {
                    "fold": int(fold),
                    "candidate_id": -1,
                    "validation_account_return_pct": 0.0,
                    "target_passed": False,
                    "risk_off": True,
                    "reason": "no current candidate for ranked families",
                }
            )
            continue
        val = float(selected["validation_account_return_pct"])
        row = {
            "fold": int(fold),
            "candidate_id": int(selected["candidate_id"]),
            "validation_account_return_pct": val,
            "target_passed": bool(val >= float(target_account_return_pct)),
            "risk_off": False,
            "reason": "selected",
            "rank_score": float(selected_family["rank_score"]) if selected_family is not None else 0.0,
            "current_selection_score": str(current_selection_score),
        }
        for col in groups:
            row[col] = selected[col]
        rows.append(row)

    folds = pd.DataFrame(rows)
    values = pd.to_numeric(folds["validation_account_return_pct"], errors="coerce").fillna(0.0)
    risk_off = folds["risk_off"].astype(bool)
    static = _summarize_candidate_families(family_outcomes, groups, target_account_return_pct=target_account_return_pct)
    aggregate = {
        "version": "v39_btcusdc_prequential_family_selector_audit",
        "folds": int(len(folds)),
        "warmup_folds": int(warmup_folds),
        "ranking_rule": str(ranking_rule),
        "group_columns": list(groups),
        "current_selection_score": str(current_selection_score),
        "target_account_return_pct": float(target_account_return_pct),
        "family_count": int(static.shape[0]),
        "prequential_active_windows": int((~risk_off).sum()),
        "prequential_risk_off_windows": int(risk_off.sum()),
        "prequential_windows_passed": int((values >= float(target_account_return_pct)).sum()),
        "prequential_windows_failed": int((~risk_off).sum() - int((values >= float(target_account_return_pct)).sum())),
        "prequential_total_validation_account_return_pct": float(values.sum()),
        "prequential_min_validation_account_return_pct": float(values.min()) if len(values) else 0.0,
        "prequential_median_validation_account_return_pct": float(values.median()) if len(values) else 0.0,
        "best_static_family_passed_windows": int(static.iloc[0]["passed_windows"]) if not static.empty else 0,
        "best_static_family_total_validation_account_return_pct": float(static.iloc[0]["total_validation_account_return_pct"]) if not static.empty else 0.0,
        "selection_rule": "each fold after warmup chooses a candidate family using only earlier completed fold outcomes, then selects the current threshold by calibration score",
        "caveat": "This audits family persistence; it is not a production L2 replay or a guarantee of future profit.",
    }
    return {"aggregate": aggregate, "folds": folds.to_dict(orient="records"), "static_family_summary": static.to_dict(orient="records")}


def audit_topk_portfolio_selector(
    evaluations: pd.DataFrame,
    *,
    score_columns: Iterable[str] = (
        "calibration_account_return_pct",
        "calibration_mean_net_pnl_bps",
        "calibration_win_rate",
        "calibration_day_positive_rate",
        "calibration_min_day_net_pnl_bps",
    ),
    topk_values: Iterable[int] = (1, 2, 3, 5, 10, 20, 50),
    min_calibration_trades: int = 20,
    min_calibration_day_positive_rate: float = 0.0,
    target_account_return_pct: float = 50.0,
) -> dict[str, object]:
    if evaluations.empty:
        raise ValueError("evaluations is empty")
    frame = evaluations.copy()
    for score in score_columns:
        if score not in frame.columns:
            raise ValueError(f"unknown score column: {score}")
    rows: list[dict[str, object]] = []
    fold_values = sorted(int(x) for x in frame["fold"].dropna().unique())
    for score in score_columns:
        for topk in topk_values:
            for fold in fold_values:
                group = frame.loc[frame["fold"] == fold].copy()
                pool = group.loc[
                    (pd.to_numeric(group["calibration_trades"], errors="coerce").fillna(0) >= int(min_calibration_trades))
                    & (pd.to_numeric(group["calibration_day_positive_rate"], errors="coerce").fillna(0) >= float(min_calibration_day_positive_rate))
                ].copy()
                if pool.empty:
                    rows.append(
                        {
                            "score_column": str(score),
                            "topk": int(topk),
                            "fold": int(fold),
                            "selected_count": 0,
                            "selected_candidate_ids": "",
                            "portfolio_validation_account_return_pct": 0.0,
                            "portfolio_validation_trades": 0.0,
                            "target_passed": False,
                            "risk_off": True,
                        }
                    )
                    continue
                selected = pool.sort_values([str(score), "candidate_id"], ascending=[False, True]).head(int(topk))
                val = float(pd.to_numeric(selected["validation_account_return_pct"], errors="coerce").fillna(0.0).mean())
                trades = float(pd.to_numeric(selected["validation_trades"], errors="coerce").fillna(0.0).mean())
                rows.append(
                    {
                        "score_column": str(score),
                        "topk": int(topk),
                        "fold": int(fold),
                        "selected_count": int(len(selected)),
                        "selected_candidate_ids": ";".join(str(int(x)) for x in selected["candidate_id"].tolist()),
                        "portfolio_validation_account_return_pct": val,
                        "portfolio_validation_trades": trades,
                        "target_passed": bool(val >= float(target_account_return_pct)),
                        "risk_off": False,
                    }
                )
    folds = pd.DataFrame(rows)
    summary = (
        folds.groupby(["score_column", "topk"], sort=True)
        .agg(
            active_windows=("risk_off", lambda s: int((~s.astype(bool)).sum())),
            risk_off_windows=("risk_off", lambda s: int(s.astype(bool).sum())),
            passed_windows=("target_passed", lambda s: int(s.astype(bool).sum())),
            total_validation_account_return_pct=("portfolio_validation_account_return_pct", "sum"),
            min_validation_account_return_pct=("portfolio_validation_account_return_pct", "min"),
            median_validation_account_return_pct=("portfolio_validation_account_return_pct", "median"),
            mean_validation_trades=("portfolio_validation_trades", "mean"),
        )
        .reset_index()
    )
    summary = summary.sort_values(
        ["passed_windows", "total_validation_account_return_pct", "min_validation_account_return_pct"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    best = summary.iloc[0].to_dict() if not summary.empty else {}
    aggregate = {
        "version": "v40_btcusdc_topk_portfolio_selector_audit",
        "folds": int(len(fold_values)),
        "target_account_return_pct": float(target_account_return_pct),
        "score_columns": [str(x) for x in score_columns],
        "topk_values": [int(x) for x in topk_values],
        "best_score_column": str(best.get("score_column", "")),
        "best_topk": int(best.get("topk", 0)) if best else 0,
        "best_passed_windows": int(best.get("passed_windows", 0)) if best else 0,
        "best_total_validation_account_return_pct": float(best.get("total_validation_account_return_pct", 0.0)) if best else 0.0,
        "best_min_validation_account_return_pct": float(best.get("min_validation_account_return_pct", 0.0)) if best else 0.0,
        "selection_rule": "select top-K candidates within each fold by calibration-only score and evaluate equal-weight average validation account return",
        "caveat": "This is a candidate-evaluation portfolio audit; it does not net overlapping live orders or prove production profitability.",
    }
    return {"aggregate": aggregate, "folds": folds.to_dict(orient="records"), "summary": summary.to_dict(orient="records")}


def audit_quantile_band_selector(
    evaluations: pd.DataFrame,
    *,
    band_columns: Iterable[str] = ("calibration_account_return_pct", "calibration_min_day_net_pnl_bps", "calibration_trades"),
    score_columns: Iterable[str] = (
        "calibration_account_return_pct",
        "calibration_min_day_net_pnl_bps",
        "calibration_win_rate",
        "calibration_day_positive_rate",
    ),
    bands: Iterable[tuple[float, float]] = ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0), (0.2, 0.8)),
    min_calibration_trades: int = 20,
    min_calibration_day_positive_rate: float = 0.0,
    target_account_return_pct: float = 50.0,
) -> dict[str, object]:
    if evaluations.empty:
        raise ValueError("evaluations is empty")
    frame = evaluations.copy()
    for column in list(band_columns) + list(score_columns):
        if column not in frame.columns:
            raise ValueError(f"unknown column: {column}")
    rows: list[dict[str, object]] = []
    fold_values = sorted(int(x) for x in frame["fold"].dropna().unique())
    for band_column in band_columns:
        for low, high in bands:
            for score_column in score_columns:
                for descending in (True, False):
                    for fold in fold_values:
                        group = frame.loc[frame["fold"] == fold].copy()
                        pool = group.loc[
                            (pd.to_numeric(group["calibration_trades"], errors="coerce").fillna(0) >= int(min_calibration_trades))
                            & (pd.to_numeric(group["calibration_day_positive_rate"], errors="coerce").fillna(0) >= float(min_calibration_day_positive_rate))
                        ].copy()
                        if pool.empty:
                            rows.append(_quantile_band_risk_off_row(band_column, low, high, score_column, descending, fold))
                            continue
                        pool["band_rank_pct"] = pd.to_numeric(pool[band_column], errors="coerce").rank(pct=True)
                        band_pool = pool.loc[(pool["band_rank_pct"] >= float(low)) & (pool["band_rank_pct"] <= float(high))].copy()
                        if band_pool.empty:
                            rows.append(_quantile_band_risk_off_row(band_column, low, high, score_column, descending, fold))
                            continue
                        selected = band_pool.sort_values([score_column, "candidate_id"], ascending=[not descending, True]).iloc[0]
                        val = float(selected["validation_account_return_pct"])
                        rows.append(
                            {
                                "band_column": str(band_column),
                                "band_low": float(low),
                                "band_high": float(high),
                                "score_column": str(score_column),
                                "score_direction": "desc" if descending else "asc",
                                "fold": int(fold),
                                "selected_candidate_id": int(selected["candidate_id"]),
                                "selected_band_rank_pct": float(selected["band_rank_pct"]),
                                "validation_account_return_pct": val,
                                "validation_trades": int(selected.get("validation_trades", 0)),
                                "target_passed": bool(val >= float(target_account_return_pct)),
                                "risk_off": False,
                            }
                        )
    folds = pd.DataFrame(rows)
    summary = (
        folds.groupby(["band_column", "band_low", "band_high", "score_column", "score_direction"], sort=True)
        .agg(
            active_windows=("risk_off", lambda s: int((~s.astype(bool)).sum())),
            risk_off_windows=("risk_off", lambda s: int(s.astype(bool).sum())),
            passed_windows=("target_passed", lambda s: int(s.astype(bool).sum())),
            total_validation_account_return_pct=("validation_account_return_pct", "sum"),
            min_validation_account_return_pct=("validation_account_return_pct", "min"),
            median_validation_account_return_pct=("validation_account_return_pct", "median"),
        )
        .reset_index()
    )
    summary = summary.sort_values(
        ["passed_windows", "total_validation_account_return_pct", "min_validation_account_return_pct"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    best = summary.iloc[0].to_dict() if not summary.empty else {}
    aggregate = {
        "version": "v42_btcusdc_quantile_band_selector_audit",
        "folds": int(len(fold_values)),
        "target_account_return_pct": float(target_account_return_pct),
        "best_band_column": str(best.get("band_column", "")),
        "best_band_low": float(best.get("band_low", 0.0)) if best else 0.0,
        "best_band_high": float(best.get("band_high", 0.0)) if best else 0.0,
        "best_score_column": str(best.get("score_column", "")),
        "best_score_direction": str(best.get("score_direction", "")),
        "best_passed_windows": int(best.get("passed_windows", 0)) if best else 0,
        "best_total_validation_account_return_pct": float(best.get("total_validation_account_return_pct", 0.0)) if best else 0.0,
        "best_min_validation_account_return_pct": float(best.get("min_validation_account_return_pct", 0.0)) if best else 0.0,
        "selection_rule": "within each fold, rank candidates by a calibration-only band column, select candidates inside a fixed percentile band, then choose one by calibration-only score",
        "caveat": "This is a selector audit; it does not prove production profitability.",
    }
    return {"aggregate": aggregate, "folds": folds.to_dict(orient="records"), "summary": summary.to_dict(orient="records")}


def _quantile_band_risk_off_row(band_column: str, low: float, high: float, score_column: str, descending: bool, fold: int) -> dict[str, object]:
    return {
        "band_column": str(band_column),
        "band_low": float(low),
        "band_high": float(high),
        "score_column": str(score_column),
        "score_direction": "desc" if descending else "asc",
        "fold": int(fold),
        "selected_candidate_id": -1,
        "selected_band_rank_pct": 0.0,
        "validation_account_return_pct": 0.0,
        "validation_trades": 0,
        "target_passed": False,
        "risk_off": True,
    }


def _nested_risk_off_row(fold: int, window: dict[str, str], target_account_return_pct: float, failure_reason: str) -> dict[str, object]:
    return {
        "fold": int(fold),
        **window,
        "selected_candidate_id": -1,
        "selected_candidate_json": "",
        "generator_trades": 0,
        "generator_total_net_pnl_bps": 0.0,
        "generator_account_return_pct": 0.0,
        "generator_win_rate": 0.0,
        "generator_day_positive_rate": 0.0,
        "selector_trades": 0,
        "selector_total_net_pnl_bps": 0.0,
        "selector_account_return_pct": 0.0,
        "selector_win_rate": 0.0,
        "selector_day_positive_rate": 0.0,
        "validation_trades": 0,
        "validation_total_net_pnl_bps": 0.0,
        "validation_account_return_pct": 0.0,
        "validation_win_rate": 0.0,
        "validation_day_positive_rate": 0.0,
        "target_account_return_pct": float(target_account_return_pct),
        "target_passed": False,
        "risk_off": True,
        "failure_reason": str(failure_reason),
    }


def _meta_selector_risk_off_row(fold: int, model_type: str, reason: str) -> dict[str, object]:
    return {
        "fold": int(fold),
        "model_type": str(model_type),
        "candidate_id": -1,
        "predicted_validation_account_return_pct": 0.0,
        "validation_account_return_pct": 0.0,
        "target_passed": False,
        "risk_off": True,
        "reason": str(reason),
    }


def _hourly_gate_row(
    fold: int,
    top_n: int,
    hours: list[int],
    validation_trades: int,
    validation_net_pnl_bps: float,
    leverage: float,
    target_account_return_pct: float,
    *,
    risk_off: bool,
) -> dict[str, object]:
    account_return = float(validation_net_pnl_bps) * float(leverage) / 100.0
    return {
        "fold": int(fold),
        "top_n_hours": int(top_n),
        "selected_hours": ";".join(str(int(h)) for h in sorted(hours)),
        "validation_trades": int(validation_trades),
        "validation_total_net_pnl_bps": float(validation_net_pnl_bps),
        "validation_account_return_pct": account_return,
        "target_passed": bool(account_return >= float(target_account_return_pct)),
        "risk_off": bool(risk_off),
    }


def _json_scalar(value: object) -> object:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if pd.isna(value):
        return None
    return value


def _make_meta_selector_model(model_type: str, history: pd.DataFrame, feature_columns: tuple[str, ...]):
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    numeric = [c for c in feature_columns if pd.api.types.is_numeric_dtype(history[c])]
    categorical = [c for c in feature_columns if c not in numeric]
    transformers = []
    if numeric:
        transformers.append(("num", Pipeline([("imputer", SimpleImputer()), ("scaler", StandardScaler())]), numeric))
    if categorical:
        transformers.append(("cat", OneHotEncoder(handle_unknown="ignore"), categorical))
    preprocessor = ColumnTransformer(transformers)
    mode = str(model_type)
    if mode == "ridge":
        model = Ridge(alpha=10.0)
    elif mode == "random_forest":
        model = RandomForestRegressor(n_estimators=200, min_samples_leaf=20, max_features=0.6, random_state=7, n_jobs=-1)
    else:
        raise ValueError(f"unsupported model_type: {model_type}")
    return Pipeline([("preprocessor", preprocessor), ("model", model)])


def _rank_candidate_families(history: pd.DataFrame, group_columns: tuple[str, ...], *, ranking_rule: str, target_account_return_pct: float) -> pd.DataFrame:
    grouped = history.groupby(list(group_columns), sort=True)
    rank = grouped.agg(
        total_validation_account_return_pct=("validation_account_return_pct", "sum"),
        mean_validation_account_return_pct=("validation_account_return_pct", "mean"),
        median_validation_account_return_pct=("validation_account_return_pct", "median"),
        min_validation_account_return_pct=("validation_account_return_pct", "min"),
        passed_windows=("validation_account_return_pct", lambda s: int((pd.to_numeric(s, errors="coerce").fillna(0.0) >= float(target_account_return_pct)).sum())),
        observed_folds=("fold", "nunique"),
    ).reset_index()
    if ranking_rule == "prior_total":
        rank["rank_score"] = rank["total_validation_account_return_pct"]
    elif ranking_rule == "prior_mean":
        rank["rank_score"] = rank["mean_validation_account_return_pct"]
    elif ranking_rule == "prior_median":
        rank["rank_score"] = rank["median_validation_account_return_pct"]
    elif ranking_rule == "prior_min_total":
        rank["rank_score"] = rank["min_validation_account_return_pct"] + 0.1 * rank["total_validation_account_return_pct"]
    elif ranking_rule == "prior_pass_total":
        rank["rank_score"] = rank["passed_windows"] * 10000.0 + rank["total_validation_account_return_pct"]
    else:
        raise ValueError(f"unsupported ranking_rule: {ranking_rule}")
    return rank.sort_values(["rank_score", "observed_folds"], ascending=[False, False]).reset_index(drop=True)


def _family_fold_outcomes(frame: pd.DataFrame, group_columns: tuple[str, ...], *, current_selection_score: str) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    rows: list[pd.Series] = []
    for _, group in frame.groupby(["fold", *group_columns], sort=True):
        sort_columns = [current_selection_score]
        ascending = [False]
        if "calibration_account_return_pct" in group.columns and current_selection_score != "calibration_account_return_pct":
            sort_columns.append("calibration_account_return_pct")
            ascending.append(False)
        sort_columns.append("candidate_id")
        ascending.append(True)
        selected = group.sort_values(sort_columns, ascending=ascending).iloc[0]
        rows.append(selected)
    return pd.DataFrame(rows).reset_index(drop=True)


def _filter_family(frame: pd.DataFrame, family: pd.Series, group_columns: tuple[str, ...]) -> pd.DataFrame:
    mask = pd.Series(True, index=frame.index)
    for col in group_columns:
        mask &= frame[col] == family[col]
    return frame.loc[mask].copy()


def _summarize_candidate_families(frame: pd.DataFrame, group_columns: tuple[str, ...], *, target_account_return_pct: float) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    summary = (
        frame.groupby(list(group_columns), sort=True)
        .agg(
            total_validation_account_return_pct=("validation_account_return_pct", "sum"),
            min_validation_account_return_pct=("validation_account_return_pct", "min"),
            median_validation_account_return_pct=("validation_account_return_pct", "median"),
            passed_windows=("validation_account_return_pct", lambda s: int((pd.to_numeric(s, errors="coerce").fillna(0.0) >= float(target_account_return_pct)).sum())),
            observed_folds=("fold", "nunique"),
        )
        .reset_index()
    )
    return summary.sort_values(
        ["passed_windows", "total_validation_account_return_pct", "min_validation_account_return_pct"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def _add_selector_policy_scores(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if "score_return_x_day" not in out.columns:
        out["score_return_x_day"] = pd.to_numeric(out["calibration_account_return_pct"], errors="coerce").fillna(0.0) * pd.to_numeric(
            out["calibration_day_positive_rate"], errors="coerce"
        ).fillna(0.0)
    if "score_mean_sqrt_trades" not in out.columns:
        trades = pd.to_numeric(out["calibration_trades"], errors="coerce").fillna(0.0).clip(lower=0.0)
        out["score_mean_sqrt_trades"] = pd.to_numeric(out["calibration_mean_net_pnl_bps"], errors="coerce").fillna(0.0) * np.sqrt(trades)
    return out


def _evaluate_selector_policy_grid(
    frame: pd.DataFrame,
    *,
    policy_scores: Iterable[str],
    direction_filters: Iterable[str],
    filter_feature_filters: Iterable[str],
    quantile_max_values: Iterable[float],
    min_calibration_trades: int,
    min_calibration_day_positive_rate: float,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    fold_groups = {int(fold): group.copy() for fold, group in frame.groupby("fold", sort=True)}
    policy_id = 0
    for score_name in policy_scores:
        if score_name not in frame.columns:
            raise ValueError(f"unknown policy score: {score_name}")
        for direction_filter in direction_filters:
            for feature_filter in filter_feature_filters:
                for quantile_max in quantile_max_values:
                    specificity = int(str(direction_filter) != "*") + int(str(feature_filter) != "*")
                    for fold, group in fold_groups.items():
                        pool = group.loc[
                            (pd.to_numeric(group["calibration_trades"], errors="coerce").fillna(0) >= int(min_calibration_trades))
                            & (
                                pd.to_numeric(group["calibration_day_positive_rate"], errors="coerce").fillna(0)
                                >= float(min_calibration_day_positive_rate)
                            )
                            & (pd.to_numeric(group["quantile"], errors="coerce").fillna(np.inf) <= float(quantile_max))
                        ].copy()
                        if str(direction_filter) != "*":
                            pool = pool.loc[pool["direction"].astype(str) == str(direction_filter)]
                        if str(feature_filter) != "*":
                            pool = pool.loc[pool["filter_feature"].astype(str) == str(feature_filter)]
                        if pool.empty:
                            rows.append(
                                {
                                    "fold": int(fold),
                                    "policy_id": int(policy_id),
                                    "candidate_id": -1,
                                    "score_name": str(score_name),
                                    "direction_filter": str(direction_filter),
                                    "filter_feature_filter": str(feature_filter),
                                    "quantile_max": float(quantile_max),
                                    "specificity": int(specificity),
                                    "validation_account_return_pct": 0.0,
                                    "risk_off": True,
                                }
                            )
                            continue
                        selected = pool.sort_values([str(score_name), "candidate_id"], ascending=[False, True]).iloc[0]
                        rows.append(
                            {
                                "fold": int(fold),
                                "policy_id": int(policy_id),
                                "candidate_id": int(selected["candidate_id"]),
                                "score_name": str(score_name),
                                "direction_filter": str(direction_filter),
                                "filter_feature_filter": str(feature_filter),
                                "quantile_max": float(quantile_max),
                                "specificity": int(specificity),
                                "validation_account_return_pct": float(selected["validation_account_return_pct"]),
                                "risk_off": False,
                            }
                        )
                    policy_id += 1
    return pd.DataFrame(rows)


def _rank_selector_policies(history: pd.DataFrame, *, ranking_rule: str, target_account_return_pct: float) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame()
    grouped = history.groupby("policy_id", sort=True)
    ranks = grouped.agg(
        prior_total_validation_account_return_pct=("validation_account_return_pct", "sum"),
        prior_mean_validation_account_return_pct=("validation_account_return_pct", "mean"),
        prior_std_validation_account_return_pct=("validation_account_return_pct", "std"),
        prior_active_windows=("risk_off", lambda s: int((~s.astype(bool)).sum())),
        prior_passed_windows=("validation_account_return_pct", lambda s: int((pd.to_numeric(s, errors="coerce").fillna(0.0) >= float(target_account_return_pct)).sum())),
        specificity=("specificity", "first"),
    ).reset_index()
    ranks = ranks.loc[ranks["prior_active_windows"] > 0].copy()
    if ranks.empty:
        return ranks
    if ranking_rule == "prior_total":
        ranks["rank_score"] = ranks["prior_total_validation_account_return_pct"]
    elif ranking_rule == "prior_pass_total":
        ranks["rank_score"] = ranks["prior_passed_windows"] * 10000.0 + ranks["prior_total_validation_account_return_pct"]
    elif ranking_rule == "prior_mean_minus_std":
        ranks["rank_score"] = ranks["prior_mean_validation_account_return_pct"] - ranks["prior_std_validation_account_return_pct"].fillna(0.0)
    else:
        raise ValueError(f"unsupported ranking_rule: {ranking_rule}")
    return ranks.sort_values(["rank_score", "specificity", "policy_id"], ascending=[False, False, True]).reset_index(drop=True)


def _summarize_selector_policies(policy_results: pd.DataFrame, *, target_account_return_pct: float) -> pd.DataFrame:
    if policy_results.empty:
        return pd.DataFrame()
    summary = (
        policy_results.groupby("policy_id", sort=True)
        .agg(
            total_validation_account_return_pct=("validation_account_return_pct", "sum"),
            min_validation_account_return_pct=("validation_account_return_pct", "min"),
            median_validation_account_return_pct=("validation_account_return_pct", "median"),
            active_windows=("risk_off", lambda s: int((~s.astype(bool)).sum())),
            passed_windows=("validation_account_return_pct", lambda s: int((pd.to_numeric(s, errors="coerce").fillna(0.0) >= float(target_account_return_pct)).sum())),
            score_name=("score_name", "first"),
            direction_filter=("direction_filter", "first"),
            filter_feature_filter=("filter_feature_filter", "first"),
            quantile_max=("quantile_max", "first"),
        )
        .reset_index()
    )
    return summary.sort_values(
        ["passed_windows", "total_validation_account_return_pct", "min_validation_account_return_pct", "policy_id"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)


def _candidate_frame(klines: pd.DataFrame, lookback: int, horizon: int) -> pd.DataFrame:
    frame = klines.copy().sort_values("timestamp").reset_index(drop=True)
    open_px = pd.to_numeric(frame["open"], errors="coerce")
    frame["lookback_return_bps"] = (open_px / open_px.shift(int(lookback)) - 1.0) * 10000.0
    frame["abs_return_bps"] = frame["lookback_return_bps"].abs()
    high = pd.to_numeric(frame["high"], errors="coerce")
    low = pd.to_numeric(frame["low"], errors="coerce")
    frame["range_bps"] = (high.shift(1).rolling(int(lookback)).max() - low.shift(1).rolling(int(lookback)).min()) / open_px.shift(int(lookback)) * 10000.0
    volume = pd.to_numeric(frame["volume"], errors="coerce")
    median_volume = volume.shift(1).rolling(int(lookback)).median()
    frame["volume_ratio"] = volume.shift(1) / median_volume
    if "signed_taker_imbalance" in frame.columns:
        flow = pd.to_numeric(frame["signed_taker_imbalance"], errors="coerce")
        frame["flow_imbalance"] = flow.shift(1).rolling(int(lookback)).mean()
        frame["abs_flow_imbalance"] = frame["flow_imbalance"].abs()
    frame["future_exit_open"] = open_px.shift(-int(horizon))
    frame["future_return_bps"] = (frame["future_exit_open"] / open_px - 1.0) * 10000.0
    if "replay_date" not in frame.columns:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame["replay_date"] = frame["timestamp"].dt.date.astype(str)
    return frame


def _candidate_signals(frame: pd.DataFrame, direction: str) -> pd.Series:
    mode = str(direction)
    if mode == "long":
        return pd.Series(1, index=frame.index)
    if mode == "short":
        return pd.Series(-1, index=frame.index)
    lookback = pd.to_numeric(frame["lookback_return_bps"], errors="coerce").fillna(0.0)
    if mode == "momentum":
        return np.sign(lookback).astype(int)
    if mode == "reversal":
        return (-np.sign(lookback)).astype(int)
    if mode == "flow_momentum":
        flow = pd.to_numeric(frame.get("flow_imbalance", pd.Series(0.0, index=frame.index)), errors="coerce").fillna(0.0)
        return np.sign(flow).astype(int)
    if mode == "flow_reversal":
        flow = pd.to_numeric(frame.get("flow_imbalance", pd.Series(0.0, index=frame.index)), errors="coerce").fillna(0.0)
        return (-np.sign(flow)).astype(int)
    raise ValueError(f"unsupported direction: {direction}")


def _non_overlapping_indices(mask: pd.Series, *, horizon: int) -> np.ndarray:
    idx = np.flatnonzero(mask.fillna(False).to_numpy(bool))
    keep: list[int] = []
    last = -10**12
    for i in idx:
        if int(i) - int(last) >= int(horizon):
            keep.append(int(i))
            last = int(i)
    return np.asarray(keep, dtype=int)


def _metric_prefix(trades: pd.DataFrame, prefix: str, *, leverage: float) -> dict[str, object]:
    pnl = pd.to_numeric(trades.get("net_pnl_bps", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    day_sums = np.asarray([], dtype=float)
    if not trades.empty and "replay_date" in trades.columns and len(pnl):
        dates = trades["replay_date"].astype(str).to_numpy()
        _, inverse = np.unique(dates, return_inverse=True)
        day_sums = np.bincount(inverse, weights=pnl.to_numpy(float))
    positive = pnl.loc[pnl > 0]
    negative = pnl.loc[pnl < 0]
    equity = pnl.cumsum().to_numpy(float) if len(pnl) else np.asarray([], dtype=float)
    if equity.size:
        running_peak = np.maximum.accumulate(np.r_[0.0, equity])[:-1]
        max_drawdown = float((running_peak - equity).max())
    else:
        max_drawdown = 0.0
    if day_sums.size >= 2:
        split = int(np.ceil(day_sums.size / 2.0))
        day_trend = float(day_sums[split:].mean() - day_sums[:split].mean()) if split < day_sums.size else 0.0
    else:
        day_trend = 0.0
    positive_sum = float(positive.sum()) if len(positive) else 0.0
    negative_sum_abs = float(abs(negative.sum()))
    profit_factor = positive_sum / negative_sum_abs if negative_sum_abs > 0 else positive_sum
    return {
        f"{prefix}_trades": int(len(pnl)),
        f"{prefix}_total_net_pnl_bps": float(pnl.sum()),
        f"{prefix}_mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
        f"{prefix}_std_net_pnl_bps": float(pnl.std(ddof=0)) if len(pnl) else 0.0,
        f"{prefix}_win_rate": float((pnl > 0).mean()) if len(pnl) else 0.0,
        f"{prefix}_account_return_pct": float(pnl.sum()) * float(leverage) / 100.0,
        f"{prefix}_positive_net_pnl_bps": positive_sum,
        f"{prefix}_negative_net_pnl_bps": float(negative.sum()) if len(negative) else 0.0,
        f"{prefix}_profit_factor": float(profit_factor),
        f"{prefix}_day_positive_rate": float((day_sums > 0).mean()) if day_sums.size else 0.0,
        f"{prefix}_min_day_net_pnl_bps": float(day_sums.min()) if day_sums.size else 0.0,
        f"{prefix}_active_day_count": int(day_sums.size),
        f"{prefix}_mean_day_net_pnl_bps": float(day_sums.mean()) if day_sums.size else 0.0,
        f"{prefix}_std_day_net_pnl_bps": float(day_sums.std(ddof=0)) if day_sums.size else 0.0,
        f"{prefix}_last_day_net_pnl_bps": float(day_sums[-1]) if day_sums.size else 0.0,
        f"{prefix}_day_net_pnl_trend_bps": day_trend,
        f"{prefix}_max_drawdown_bps": max_drawdown,
    }


def _daily_metrics(trades: pd.DataFrame, *, leverage: float) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=["replay_date", "trades", "total_net_pnl_bps", "account_return_pct"])
    rows: list[dict[str, object]] = []
    for day, group in trades.groupby("replay_date", sort=True):
        pnl = pd.to_numeric(group["net_pnl_bps"], errors="coerce").fillna(0.0)
        rows.append(
            {
                "replay_date": str(day),
                "trades": int(len(group)),
                "total_net_pnl_bps": float(pnl.sum()),
                "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                "win_rate": float((pnl > 0).mean()) if len(pnl) else 0.0,
                "account_return_pct": float(pnl.sum()) * float(leverage) / 100.0,
            }
        )
    return pd.DataFrame(rows)


def _write_report(path: Path, aggregate: dict[str, object], selected: pd.Series, cal_trades: pd.DataFrame, val_trades: pd.DataFrame, evaluations: pd.DataFrame) -> None:
    top = evaluations.sort_values(
        ["calibration_total_net_pnl_bps", "calibration_day_positive_rate", "calibration_mean_net_pnl_bps"],
        ascending=[False, False, False],
    ).head(20)
    lines = [
        "# V27 BTCUSDC Independent Validation",
        "",
        "V27 selects a simple BTCUSDC public 1m kline candidate on calibration dates only, then applies the frozen selected candidate to later validation dates.",
        "",
        "## Aggregate",
        "",
        "```json",
        json.dumps(aggregate, indent=2),
        "```",
        "",
        "## Selected Candidate Row",
        "",
        pd.DataFrame([selected.to_dict()]).to_csv(index=False).strip(),
        "",
        "## Top Calibration Candidates",
        "",
        top.to_csv(index=False).strip(),
        "",
        "## Calibration Trades",
        "",
        cal_trades.to_csv(index=False).strip(),
        "",
        "## Validation Trades",
        "",
        val_trades.to_csv(index=False).strip(),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _infer_interval(path: Path) -> str:
    parts = path.name.split("-")
    return parts[1] if len(parts) >= 3 else "1m"


def _rolling_windows(*, start_date: str, end_date: str, calibration_days: int, validation_days: int, step_days: int) -> list[dict[str, str]]:
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    windows: list[dict[str, str]] = []
    cur = start
    while True:
        cal_start = cur
        cal_end = cal_start + pd.Timedelta(days=int(calibration_days) - 1)
        val_start = cal_end + pd.Timedelta(days=1)
        val_end = val_start + pd.Timedelta(days=int(validation_days) - 1)
        if val_end > end:
            break
        windows.append(
            {
                "calibration_start": cal_start.date().isoformat(),
                "calibration_end": cal_end.date().isoformat(),
                "validation_start": val_start.date().isoformat(),
                "validation_end": val_end.date().isoformat(),
            }
        )
        cur = cur + pd.Timedelta(days=int(step_days))
    return windows


def _write_rolling_report(path: Path, aggregate: dict[str, object], folds: pd.DataFrame) -> None:
    lines = [
        "# V28 BTCUSDC Rolling Forward Validation",
        "",
        "V28 repeats BTCUSDC public 1m kline candidate selection across rolling calibration windows and validates each selected candidate on the following forward window.",
        "",
        "## Aggregate",
        "",
        "```json",
        json.dumps(aggregate, indent=2),
        "```",
        "",
        "## Fold Metrics",
        "",
        folds.to_csv(index=False).strip(),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_nested_report(path: Path, aggregate: dict[str, object], folds: pd.DataFrame) -> None:
    lines = [
        "# V43 BTCUSDC Nested Recency Validation",
        "",
        "V43 splits each calibration window into an early candidate-generator slice and a later selector slice before forward validation.",
        "",
        "## Aggregate",
        "",
        "```json",
        json.dumps(aggregate, indent=2),
        "```",
        "",
        "## Fold Metrics",
        "",
        folds.to_csv(index=False).strip(),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _dedupe_threshold_quantiles(values: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    seen: set[float] = set()
    for value, quantile in values:
        rounded = round(float(value), 12)
        if rounded in seen:
            continue
        seen.add(rounded)
        out.append((float(value), float(quantile)))
    return out
