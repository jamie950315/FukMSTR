from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import (
    BTCUSDCCandidate,
    _candidate_frame,
    _candidate_signals,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_btcusdc_v90_forward_monitoring as v90


OUT_DIR = ROOT / "runs" / "research_v94_btcusdc_high_frequency_scan"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V94_BTCUSDC_HIGH_FREQUENCY_SCAN_RESULTS.md"

LOOKBACKS = (15, 30, 60, 120, 240)
HORIZONS = (15, 30, 60)
DIRECTIONS = ("flow_momentum", "flow_reversal", "momentum", "reversal")
FILTER_FEATURES = ("abs_flow_imbalance", "range_bps")
QUANTILES = (0.0, 0.5, 0.75, 0.9)
FEE_BPS = 8.5
HOLDOUT_DAYS = 365

MIN_WIN_RATE = 0.55
MIN_AVG_TRADES_PER_CALENDAR_DAY = 1.0
MIN_CALENDAR_POSITIVE_MONTH_RATE = 0.50


def _spaced_indices(mask: pd.Series, *, horizon: int) -> np.ndarray:
    idx = np.flatnonzero(mask.fillna(False).to_numpy(bool))
    keep: list[int] = []
    pos = 0
    spacing = int(horizon)
    while pos < len(idx):
        current = int(idx[pos])
        keep.append(current)
        pos = int(np.searchsorted(idx, current + spacing, side="left"))
    return np.asarray(keep, dtype=int)


def _full_bars() -> pd.DataFrame:
    base_bars = v90._load_base_bars(v90.V50_BARS)
    base_end = base_bars["timestamp"].max()
    new_paths = v90._new_aggtrade_paths(base_end)
    bars, _ = v90._combined_bars(base_bars, new_paths)
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    return bars.sort_values("timestamp").reset_index(drop=True)


def _trade_summary(trades: pd.DataFrame, *, start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> dict[str, object]:
    start_ts = pd.to_datetime(start_ts, utc=True)
    end_ts = pd.to_datetime(end_ts, utc=True)
    calendar_days = pd.date_range(start=start_ts.normalize(), end=end_ts.normalize(), freq="D")
    calendar_months = pd.period_range(
        start=start_ts.tz_convert(None).to_period("M"),
        end=end_ts.tz_convert(None).to_period("M"),
        freq="M",
    )
    if trades.empty:
        return {
            "trade_count": 0,
            "total_net_pnl_bps": 0.0,
            "mean_net_pnl_bps": 0.0,
            "win_rate": 0.0,
            "max_drawdown_bps": 0.0,
            "calendar_day_count": int(len(calendar_days)),
            "active_day_count": 0,
            "avg_trades_per_calendar_day": 0.0,
            "active_day_rate": 0.0,
            "calendar_positive_month_rate": 0.0,
            "active_positive_month_rate": 0.0,
            "worst_month_net_pnl_bps": 0.0,
        }

    frame = trades.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["net_pnl_bps"] = pd.to_numeric(frame["net_pnl_bps"], errors="coerce").fillna(0.0)
    scoped = frame.loc[(frame["timestamp"] >= start_ts) & (frame["timestamp"] <= end_ts)].copy()
    pnl = scoped["net_pnl_bps"] if len(scoped) else pd.Series(dtype=float)
    equity = pnl.cumsum()
    drawdown = equity.cummax() - equity
    active_days = scoped["timestamp"].dt.normalize().nunique() if len(scoped) else 0

    if len(scoped):
        scoped["_month_period"] = scoped["timestamp"].dt.tz_convert(None).dt.to_period("M")
        month_totals = scoped.groupby("_month_period", sort=True)["net_pnl_bps"].sum().reindex(calendar_months, fill_value=0.0)
    else:
        month_totals = pd.Series(0.0, index=calendar_months, dtype=float)
    active_month_totals = month_totals.loc[month_totals != 0.0]

    return {
        "trade_count": int(len(scoped)),
        "total_net_pnl_bps": float(pnl.sum()) if len(pnl) else 0.0,
        "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
        "win_rate": float((pnl > 0.0).mean()) if len(pnl) else 0.0,
        "max_drawdown_bps": float(drawdown.max()) if len(drawdown) else 0.0,
        "calendar_day_count": int(len(calendar_days)),
        "active_day_count": int(active_days),
        "avg_trades_per_calendar_day": float(len(scoped) / len(calendar_days)) if len(calendar_days) else 0.0,
        "active_day_rate": float(active_days / len(calendar_days)) if len(calendar_days) else 0.0,
        "calendar_positive_month_rate": float((month_totals > 0.0).mean()) if len(month_totals) else 0.0,
        "active_positive_month_rate": float((active_month_totals > 0.0).mean()) if len(active_month_totals) else 0.0,
        "worst_month_net_pnl_bps": float(month_totals.min()) if len(month_totals) else 0.0,
    }


def _passes_high_frequency_gate(row: dict[str, object]) -> bool:
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


def _candidate_ledger_from_frame(frame: pd.DataFrame, candidate: BTCUSDCCandidate) -> pd.DataFrame:
    feature = pd.to_numeric(frame[candidate.filter_feature], errors="coerce")
    signals = _candidate_signals(frame, candidate.direction)
    eligible = feature >= float(candidate.threshold)
    eligible &= signals != 0
    eligible &= pd.to_numeric(frame["future_exit_open"], errors="coerce").notna()
    keep_idx = _spaced_indices(eligible, horizon=int(candidate.horizon_minutes))
    if keep_idx.size == 0:
        return pd.DataFrame(columns=["timestamp", "replay_date", "signal", "entry_px", "exit_px", "gross_pnl_bps", "net_pnl_bps"])

    open_px = pd.to_numeric(frame["open"], errors="coerce").to_numpy(float)
    future_exit = pd.to_numeric(frame["future_exit_open"], errors="coerce").to_numpy(float)
    selected = frame.iloc[keep_idx].copy()
    selected_signal = signals.iloc[keep_idx].astype(int).to_numpy()
    entry_px = open_px[keep_idx]
    exit_px = future_exit[keep_idx]
    gross = (exit_px / entry_px - 1.0) * 10000.0 * selected_signal
    trades = pd.DataFrame(
        {
            "timestamp": selected["timestamp"].to_numpy(),
            "replay_date": selected["replay_date"].to_numpy(),
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
            "direction": str(candidate.direction),
            "filter_feature": str(candidate.filter_feature),
            "threshold": float(candidate.threshold),
            "quantile": np.nan if candidate.quantile is None else float(candidate.quantile),
            "fee_bps": float(candidate.fee_bps),
        }
    )
    trades["equity_bps"] = pd.to_numeric(trades["net_pnl_bps"], errors="coerce").fillna(0.0).cumsum()
    return trades


def _evaluate_candidate(
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
) -> tuple[dict[str, object], pd.DataFrame]:
    design_feature = pd.to_numeric(frame.loc[frame["timestamp"] < design_end_ts, filter_feature], errors="coerce").dropna()
    if design_feature.empty:
        return {}, pd.DataFrame()
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
    ledger = _candidate_ledger_from_frame(frame, candidate)
    full = _trade_summary(ledger, start_ts=full_start_ts, end_ts=full_end_ts)
    holdout = _trade_summary(ledger, start_ts=holdout_start_ts, end_ts=full_end_ts)
    row = {
        "policy_id": f"lb{lookback}_h{horizon}_{direction}_{filter_feature}_q{quantile:g}",
        "lookback_minutes": int(lookback),
        "horizon_minutes": int(horizon),
        "direction": str(direction),
        "filter_feature": str(filter_feature),
        "threshold": threshold,
        "quantile": float(quantile),
        "fee_bps": float(FEE_BPS),
        **{f"full_{key}": value for key, value in full.items()},
        **{f"holdout_{key}": value for key, value in holdout.items()},
    }
    row["passed_high_frequency_gate"] = bool(_passes_high_frequency_gate(row))
    return row, ledger


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
            if "replay_date" not in frame.columns:
                frame["replay_date"] = frame["timestamp"].dt.date.astype(str)
            for direction in DIRECTIONS:
                for filter_feature in FILTER_FEATURES:
                    if filter_feature not in frame.columns:
                        continue
                    for quantile in QUANTILES:
                        evaluated += 1
                        if evaluated % 50 == 0:
                            print(f"evaluated {evaluated} high-frequency candidates", flush=True)
                        row, ledger = _evaluate_candidate(
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
                        if not row:
                            continue
                        rows.append(row)
                        if bool(row["passed_high_frequency_gate"]):
                            ledgers[str(row["policy_id"])] = ledger

    candidates = pd.DataFrame(rows)
    if not candidates.empty:
        candidates = candidates.sort_values(
            [
                "passed_high_frequency_gate",
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
    top = candidates.head(10).copy() if not candidates.empty else pd.DataFrame()
    report_cols = [
        "policy_id",
        "passed_high_frequency_gate",
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
    lines = [
        "# Research V94 BTCUSDC High-Frequency Scan Results",
        "",
        "## Decision",
        "",
        f"- Evaluated candidates: `{payload['scan']['evaluated_candidate_count']}`",
        f"- Passing high-frequency candidates: `{payload['decision']['passing_candidate_count']}`",
        f"- Selected candidate: `{payload['decision']['selected_policy']}`",
        f"- Gate: full and holdout total PnL > 0, win rate > {MIN_WIN_RATE:.2%}, average trades/day >= {MIN_AVG_TRADES_PER_CALENDAR_DAY}, calendar-positive months >= {MIN_CALENDAR_POSITIVE_MONTH_RATE:.2%}",
        f"- Grid: focused first-pass scan over lookbacks `{list(LOOKBACKS)}`, horizons `{list(HORIZONS)}`, directions `{list(DIRECTIONS)}`, filters `{list(FILTER_FEATURES)}`, quantiles `{list(QUANTILES)}`",
        "",
        "## Top Candidates",
        "",
        top[report_cols].to_csv(index=False).strip() if not top.empty else "No candidates were produced.",
        "",
        "## Passing Candidates",
        "",
        passed[report_cols].to_csv(index=False).strip() if not passed.empty else "No candidate passed the high-frequency gate.",
        "",
        "## Interpretation",
        "",
        "V94 is a high-frequency candidate scan on BTCUSDC 1m aggTrade flow bars. Thresholds are computed on the design window and then applied to the full and holdout windows. This is a research scan, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    bars = _full_bars()
    candidates, ledgers, meta = _scan_candidates(bars)
    passed = candidates.loc[candidates["passed_high_frequency_gate"]].copy() if not candidates.empty else pd.DataFrame()

    candidates_path = OUT_DIR / "v94_high_frequency_candidates.csv"
    passed_path = OUT_DIR / "v94_high_frequency_passed_candidates.csv"
    candidates.to_csv(candidates_path, index=False)
    passed.to_csv(passed_path, index=False)
    for policy_id, ledger in ledgers.items():
        safe_id = policy_id.replace("/", "_")
        ledger.to_csv(OUT_DIR / f"v94_{safe_id}_trade_ledger.csv", index=False)

    selected = str(passed.iloc[0]["policy_id"]) if not passed.empty else None
    payload = {
        "version": "v94_btcusdc_high_frequency_scan",
        "scan": meta,
        "grid": {
            "lookbacks": list(LOOKBACKS),
            "horizons": list(HORIZONS),
            "directions": list(DIRECTIONS),
            "filter_features": list(FILTER_FEATURES),
            "quantiles": list(QUANTILES),
            "fee_bps": FEE_BPS,
            "holdout_days": HOLDOUT_DAYS,
        },
        "decision": {
            "passing_candidate_count": int(len(passed)),
            "selected_policy": selected,
            "goal_satisfied_by_scan": bool(selected is not None),
            "failed_reason": None if selected is not None else "no candidate passed the high-frequency profitability, win-rate, frequency, and month-stability gate",
        },
        "outputs": {
            "candidates": str(candidates_path),
            "passed_candidates": str(passed_path),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v94_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload, candidates, passed)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
