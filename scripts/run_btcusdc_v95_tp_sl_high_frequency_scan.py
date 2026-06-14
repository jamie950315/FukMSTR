from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import BTCUSDCCandidate, _candidate_frame, _candidate_signals


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_btcusdc_v94_high_frequency_scan as v94


OUT_DIR = ROOT / "runs" / "research_v95_btcusdc_tp_sl_high_frequency_scan"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V95_BTCUSDC_TP_SL_HIGH_FREQUENCY_SCAN_RESULTS.md"

LOOKBACKS = (60, 120, 240)
HORIZONS = (60, 120)
DIRECTIONS = ("flow_reversal", "reversal")
FILTER_FEATURES = ("range_bps",)
QUANTILES = (0.9,)
TAKE_PROFIT_BPS = (10.0, 15.0, 20.0, 30.0)
STOP_LOSS_BPS = (10.0, 15.0, 20.0, 30.0, 40.0, 60.0)
FEE_BPS = 8.5
HOLDOUT_DAYS = 365

MIN_WIN_RATE = 0.55
MIN_AVG_TRADES_PER_CALENDAR_DAY = 1.0
MIN_CALENDAR_POSITIVE_MONTH_RATE = 0.50


def _signal_array(signal_values: pd.Series | np.ndarray, entry_indices: np.ndarray) -> np.ndarray:
    if isinstance(signal_values, pd.Series):
        return pd.to_numeric(signal_values.reindex(entry_indices), errors="coerce").fillna(0).astype(int).to_numpy()
    values = np.asarray(signal_values, dtype=int)
    return values[entry_indices]


def _barrier_ledger(
    frame: pd.DataFrame,
    *,
    entry_idx: pd.Index | np.ndarray,
    signal_values: pd.Series | np.ndarray,
    horizon_minutes: int,
    take_profit_bps: float,
    stop_loss_bps: float,
    fee_bps: float,
) -> pd.DataFrame:
    entry_indices = np.asarray(entry_idx, dtype=int)
    horizon = int(horizon_minutes)
    valid = entry_indices + horizon < len(frame)
    entry_indices = entry_indices[valid]
    if entry_indices.size == 0:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "exit_timestamp",
                "signal",
                "entry_px",
                "exit_px",
                "exit_reason",
                "gross_pnl_bps",
                "net_pnl_bps",
                "horizon_minutes",
                "take_profit_bps",
                "stop_loss_bps",
                "fee_bps",
            ]
        )

    signals = _signal_array(signal_values, entry_indices)
    open_px = pd.to_numeric(frame["open"], errors="coerce").to_numpy(float)
    high_px = pd.to_numeric(frame["high"], errors="coerce").to_numpy(float)
    low_px = pd.to_numeric(frame["low"], errors="coerce").to_numpy(float)
    timestamps = pd.to_datetime(frame["timestamp"], utc=True).to_numpy()

    entry_px = open_px[entry_indices]
    exit_indices = entry_indices + horizon
    gross = (open_px[exit_indices] / entry_px - 1.0) * 10000.0 * signals
    reason = np.full(entry_indices.shape, "horizon", dtype=object)
    active = np.ones(entry_indices.shape, dtype=bool)

    tp = float(take_profit_bps)
    sl = float(stop_loss_bps)
    for offset in range(1, horizon + 1):
        active_positions = np.flatnonzero(active)
        if active_positions.size == 0:
            break
        src = entry_indices[active_positions]
        dst = src + offset
        sig = signals[active_positions]
        entry = entry_px[active_positions]

        long_side = sig > 0
        tp_hit = np.zeros(active_positions.shape, dtype=bool)
        sl_hit = np.zeros(active_positions.shape, dtype=bool)
        if long_side.any():
            long_pos = np.flatnonzero(long_side)
            tp_hit[long_pos] = (high_px[dst[long_pos]] / entry[long_pos] - 1.0) * 10000.0 >= tp
            sl_hit[long_pos] = (low_px[dst[long_pos]] / entry[long_pos] - 1.0) * 10000.0 <= -sl
        short_side = ~long_side
        if short_side.any():
            short_pos = np.flatnonzero(short_side)
            tp_hit[short_pos] = (low_px[dst[short_pos]] / entry[short_pos] - 1.0) * 10000.0 <= -tp
            sl_hit[short_pos] = (high_px[dst[short_pos]] / entry[short_pos] - 1.0) * 10000.0 >= sl

        stop_positions = active_positions[sl_hit]
        if stop_positions.size:
            gross[stop_positions] = -sl
            exit_indices[stop_positions] = entry_indices[stop_positions] + offset
            reason[stop_positions] = "stop_loss"
            active[stop_positions] = False

        tp_only_positions = active_positions[tp_hit & ~sl_hit]
        if tp_only_positions.size:
            gross[tp_only_positions] = tp
            exit_indices[tp_only_positions] = entry_indices[tp_only_positions] + offset
            reason[tp_only_positions] = "take_profit"
            active[tp_only_positions] = False

    ledger = pd.DataFrame(
        {
            "timestamp": timestamps[entry_indices],
            "exit_timestamp": timestamps[exit_indices],
            "signal": signals,
            "entry_px": entry_px,
            "exit_px": open_px[exit_indices],
            "exit_reason": reason,
            "gross_pnl_bps": gross,
            "net_pnl_bps": gross - float(fee_bps),
            "horizon_minutes": horizon,
            "take_profit_bps": float(take_profit_bps),
            "stop_loss_bps": float(stop_loss_bps),
            "fee_bps": float(fee_bps),
        }
    )
    ledger["equity_bps"] = pd.to_numeric(ledger["net_pnl_bps"], errors="coerce").fillna(0.0).cumsum()
    return ledger


def _passes_tp_sl_gate(row: dict[str, object]) -> bool:
    return (
        float(row["full_total_net_pnl_bps"]) > 0.0
        and float(row["holdout_total_net_pnl_bps"]) > 0.0
        and float(row["full_win_rate"]) > MIN_WIN_RATE
        and float(row["holdout_win_rate"]) > MIN_WIN_RATE
        and float(row["full_avg_trades_per_calendar_day"]) >= MIN_AVG_TRADES_PER_CALENDAR_DAY
        and float(row["holdout_avg_trades_per_calendar_day"]) >= MIN_AVG_TRADES_PER_CALENDAR_DAY
        and float(row["full_calendar_positive_month_rate"]) >= MIN_CALENDAR_POSITIVE_MONTH_RATE
        and float(row["holdout_calendar_positive_month_rate"]) >= MIN_CALENDAR_POSITIVE_MONTH_RATE
    )


def _base_entries(frame: pd.DataFrame, candidate: BTCUSDCCandidate) -> tuple[np.ndarray, np.ndarray]:
    feature = pd.to_numeric(frame[candidate.filter_feature], errors="coerce")
    signals = _candidate_signals(frame, candidate.direction).astype(int)
    eligible = feature >= float(candidate.threshold)
    eligible &= signals != 0
    eligible &= pd.to_numeric(frame["future_exit_open"], errors="coerce").notna()
    return v94._spaced_indices(eligible, horizon=int(candidate.horizon_minutes)), signals.to_numpy(int)


def _evaluate_setup(
    frame: pd.DataFrame,
    *,
    lookback: int,
    horizon: int,
    direction: str,
    filter_feature: str,
    quantile: float,
    design_end_ts: pd.Timestamp,
    full_start_ts: pd.Timestamp,
    full_end_ts: pd.Timestamp,
    holdout_start_ts: pd.Timestamp,
) -> list[tuple[dict[str, object], pd.DataFrame]]:
    design_feature = pd.to_numeric(frame.loc[frame["timestamp"] < design_end_ts, filter_feature], errors="coerce").dropna()
    if design_feature.empty:
        return []
    threshold = float(design_feature.quantile(float(quantile)))
    candidate = BTCUSDCCandidate(
        lookback_minutes=int(lookback),
        horizon_minutes=int(horizon),
        direction=str(direction),
        filter_feature=str(filter_feature),
        threshold=threshold,
        fee_bps=FEE_BPS,
        quantile=float(quantile),
    )
    entry_idx, signals = _base_entries(frame, candidate)
    if entry_idx.size == 0:
        return []

    rows: list[tuple[dict[str, object], pd.DataFrame]] = []
    for take_profit in TAKE_PROFIT_BPS:
        for stop_loss in STOP_LOSS_BPS:
            ledger = _barrier_ledger(
                frame,
                entry_idx=entry_idx,
                signal_values=signals,
                horizon_minutes=int(horizon),
                take_profit_bps=float(take_profit),
                stop_loss_bps=float(stop_loss),
                fee_bps=FEE_BPS,
            )
            full = v94._trade_summary(ledger, start_ts=full_start_ts, end_ts=full_end_ts)
            holdout = v94._trade_summary(ledger, start_ts=holdout_start_ts, end_ts=full_end_ts)
            row = {
                "policy_id": f"lb{lookback}_h{horizon}_{direction}_{filter_feature}_q{quantile:g}_tp{take_profit:g}_sl{stop_loss:g}",
                "lookback_minutes": int(lookback),
                "horizon_minutes": int(horizon),
                "direction": str(direction),
                "filter_feature": str(filter_feature),
                "threshold": threshold,
                "quantile": float(quantile),
                "take_profit_bps": float(take_profit),
                "stop_loss_bps": float(stop_loss),
                "fee_bps": float(FEE_BPS),
                **{f"full_{key}": value for key, value in full.items()},
                **{f"holdout_{key}": value for key, value in holdout.items()},
            }
            row["passed_tp_sl_gate"] = bool(_passes_tp_sl_gate(row))
            rows.append((row, ledger))
    return rows


def _scan_candidates(bars: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], dict[str, object]]:
    full_start_ts = pd.to_datetime(bars["timestamp"].min(), utc=True)
    full_end_ts = pd.to_datetime(bars["timestamp"].max(), utc=True)
    holdout_start_ts = full_end_ts - pd.Timedelta(days=HOLDOUT_DAYS)
    design_end_ts = holdout_start_ts
    rows: list[dict[str, object]] = []
    ledgers: dict[str, pd.DataFrame] = {}
    evaluated = 0

    for lookback in LOOKBACKS:
        for horizon in HORIZONS:
            frame = _candidate_frame(bars, int(lookback), int(horizon))
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
            for direction in DIRECTIONS:
                for filter_feature in FILTER_FEATURES:
                    if filter_feature not in frame.columns:
                        continue
                    for quantile in QUANTILES:
                        setup_rows = _evaluate_setup(
                            frame,
                            lookback=int(lookback),
                            horizon=int(horizon),
                            direction=str(direction),
                            filter_feature=str(filter_feature),
                            quantile=float(quantile),
                            design_end_ts=design_end_ts,
                            full_start_ts=full_start_ts,
                            full_end_ts=full_end_ts,
                            holdout_start_ts=holdout_start_ts,
                        )
                        for row, ledger in setup_rows:
                            evaluated += 1
                            rows.append(row)
                            if bool(row["passed_tp_sl_gate"]):
                                ledgers[str(row["policy_id"])] = ledger
                        if setup_rows:
                            print(f"evaluated {evaluated} TP/SL candidates", flush=True)

    candidates = pd.DataFrame(rows)
    if not candidates.empty:
        candidates = candidates.sort_values(
            [
                "passed_tp_sl_gate",
                "holdout_total_net_pnl_bps",
                "holdout_win_rate",
                "full_total_net_pnl_bps",
                "full_avg_trades_per_calendar_day",
            ],
            ascending=[False, False, False, False, False],
        ).reset_index(drop=True)
    meta = {
        "full_start_timestamp": full_start_ts.isoformat(),
        "full_end_timestamp": full_end_ts.isoformat(),
        "holdout_start_timestamp": holdout_start_ts.isoformat(),
        "design_end_timestamp": design_end_ts.isoformat(),
        "evaluated_candidate_count": int(evaluated),
        "emitted_candidate_count": int(len(candidates)),
    }
    return candidates, ledgers, meta


def _write_report(payload: dict[str, object], candidates: pd.DataFrame, passed: pd.DataFrame) -> None:
    report_cols = [
        "policy_id",
        "passed_tp_sl_gate",
        "full_trade_count",
        "full_avg_trades_per_calendar_day",
        "full_total_net_pnl_bps",
        "full_win_rate",
        "full_calendar_positive_month_rate",
        "holdout_trade_count",
        "holdout_avg_trades_per_calendar_day",
        "holdout_total_net_pnl_bps",
        "holdout_win_rate",
        "holdout_calendar_positive_month_rate",
    ]
    top = candidates.head(10).copy() if not candidates.empty else pd.DataFrame()
    lines = [
        "# Research V95 BTCUSDC TP/SL High-Frequency Scan Results",
        "",
        "## Decision",
        "",
        f"- Evaluated candidates: `{payload['scan']['evaluated_candidate_count']}`",
        f"- Passing TP/SL high-frequency candidates: `{payload['decision']['passing_candidate_count']}`",
        f"- Selected candidate: `{payload['decision']['selected_policy']}`",
        f"- Gate: full and holdout total PnL > 0, win rate > {MIN_WIN_RATE:.2%}, average trades/day >= {MIN_AVG_TRADES_PER_CALENDAR_DAY}, calendar-positive months >= {MIN_CALENDAR_POSITIVE_MONTH_RATE:.2%}",
        "",
        "## Top Candidates",
        "",
        top[report_cols].to_csv(index=False).strip() if not top.empty else "No candidates were produced.",
        "",
        "## Passing Candidates",
        "",
        passed[report_cols].to_csv(index=False).strip() if not passed.empty else "No candidate passed the TP/SL high-frequency gate.",
        "",
        "## Interpretation",
        "",
        "V95 tests TP/SL exits on BTCUSDC 1m aggTrade flow bars. Same-bar TP/SL collisions are counted as stop-losses. Thresholds are computed on the design window and then applied to the full and holdout windows. This is a research scan, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    bars = v94._full_bars()
    candidates, ledgers, meta = _scan_candidates(bars)
    passed = candidates.loc[candidates["passed_tp_sl_gate"]].copy() if not candidates.empty else pd.DataFrame()

    candidates_path = OUT_DIR / "v95_tp_sl_high_frequency_candidates.csv"
    passed_path = OUT_DIR / "v95_tp_sl_high_frequency_passed_candidates.csv"
    candidates.to_csv(candidates_path, index=False)
    passed.to_csv(passed_path, index=False)
    for policy_id, ledger in ledgers.items():
        ledger.to_csv(OUT_DIR / f"v95_{policy_id}_trade_ledger.csv", index=False)

    selected = str(passed.iloc[0]["policy_id"]) if not passed.empty else None
    payload = {
        "version": "v95_btcusdc_tp_sl_high_frequency_scan",
        "scan": meta,
        "grid": {
            "lookbacks": list(LOOKBACKS),
            "horizons": list(HORIZONS),
            "directions": list(DIRECTIONS),
            "filter_features": list(FILTER_FEATURES),
            "quantiles": list(QUANTILES),
            "take_profit_bps": list(TAKE_PROFIT_BPS),
            "stop_loss_bps": list(STOP_LOSS_BPS),
            "fee_bps": FEE_BPS,
            "holdout_days": HOLDOUT_DAYS,
        },
        "decision": {
            "passing_candidate_count": int(len(passed)),
            "selected_policy": selected,
            "goal_satisfied_by_scan": bool(selected is not None),
            "failed_reason": None if selected is not None else "no candidate passed the TP/SL high-frequency profitability, win-rate, frequency, and month-stability gate",
        },
        "outputs": {
            "candidates": str(candidates_path),
            "passed_candidates": str(passed_path),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v95_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload, candidates, passed)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
