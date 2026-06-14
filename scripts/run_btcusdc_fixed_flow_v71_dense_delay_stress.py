from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import (
    BTCUSDCCandidate,
    build_delayed_candidate_trade_ledger_grid,
    summarize_delay_stress_grid,
)


ROOT = Path(__file__).resolve().parents[1]
INPUT_BARS = ROOT / "runs" / "research_v50_btcusdc_full_aggtrade_flow_input" / "btcusdc_full_aggtrade_1m_flow_bars.csv"
V68_SUMMARY = ROOT / "runs" / "research_v68_btcusdc_fixed_flow_stability" / "v68_summary.json"
V68_BASE_LEDGER = ROOT / "runs" / "research_v68_btcusdc_fixed_flow_stability" / "v68_base_trade_ledger.csv"
V69_SUMMARY = ROOT / "runs" / "research_v69_btcusdc_fixed_flow_hour_gate" / "v69_summary.json"
V69_LEDGER = ROOT / "runs" / "research_v69_btcusdc_fixed_flow_hour_gate" / "v69_hour_gated_trade_ledger.csv"
V70_PERIOD_SUMMARY = ROOT / "runs" / "research_v70_btcusdc_fixed_flow_extended_validation" / "v70_period_summary.csv"

OUT_DIR = ROOT / "runs" / "research_v71_btcusdc_fixed_flow_dense_delay_stress"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V71_FIXED_FLOW_DENSE_DELAY_STRESS_RESULTS.md"

LEVERAGE = 8.0
ENTRY_DELAYS = tuple(range(0, 121))


def _load_bars(path: Path) -> pd.DataFrame:
    bars = pd.read_csv(path)
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    if "replay_date" not in bars.columns:
        bars["replay_date"] = bars["timestamp"].dt.date.astype(str)
    return bars.sort_values("timestamp").reset_index(drop=True)


def _load_trades(path: Path) -> pd.DataFrame:
    trades = pd.read_csv(path)
    trades["timestamp"] = pd.to_datetime(trades["timestamp"], utc=True)
    trades["net_pnl_bps"] = pd.to_numeric(trades["net_pnl_bps"], errors="coerce").fillna(0.0)
    return trades.sort_values("timestamp").reset_index(drop=True)


def _candidate_from_v68(summary: dict[str, object]) -> BTCUSDCCandidate:
    candidate = summary["candidate"]
    if not isinstance(candidate, dict):
        raise ValueError("v68 summary missing candidate")
    return BTCUSDCCandidate(
        lookback_minutes=int(candidate["lookback_minutes"]),
        horizon_minutes=int(candidate["horizon_minutes"]),
        direction=str(candidate["direction"]),
        filter_feature=str(candidate["filter_feature"]),
        threshold=float(candidate["threshold"]),
        fee_bps=float(candidate["fee_bps"]),
        quantile=float(candidate["quantile"]) if candidate.get("quantile") is not None else None,
    )


def _date_to_fold_map(base_ledger: pd.DataFrame) -> dict[str, int]:
    required = {"replay_date", "fold"}
    missing = required.difference(base_ledger.columns)
    if missing:
        raise ValueError(f"base ledger missing columns: {sorted(missing)}")
    dates = base_ledger[["replay_date", "fold"]].dropna().copy()
    dates["replay_date"] = dates["replay_date"].astype(str)
    dates["fold"] = pd.to_numeric(dates["fold"], errors="coerce").astype("Int64")
    return {str(row.replay_date): int(row.fold) for row in dates.dropna().itertuples(index=False)}


def _apply_locked_hour_gate(delayed: pd.DataFrame, *, excluded_hours: list[int], gate_mode: str, date_to_fold: dict[str, int]) -> pd.DataFrame:
    frame = delayed.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["signal_timestamp"] = pd.to_datetime(frame["signal_timestamp"], utc=True)
    frame["entry_hour"] = frame["timestamp"].dt.hour.astype(int)
    frame["signal_hour"] = frame["signal_timestamp"].dt.hour.astype(int)
    if gate_mode == "signal_hour":
        gate_hour = frame["signal_hour"]
    elif gate_mode == "entry_hour":
        gate_hour = frame["entry_hour"]
    else:
        raise ValueError(f"unsupported gate_mode: {gate_mode}")
    kept = frame.loc[~gate_hour.isin([int(x) for x in excluded_hours])].copy()
    kept["fold"] = kept["replay_date"].astype(str).map(date_to_fold).astype("Int64")
    return kept.dropna(subset=["fold"]).copy()


def _period_loss_run_summary(period_summary: pd.DataFrame) -> dict[str, object]:
    rows = period_summary.sort_values(["period_type", "period"]).copy()
    output: dict[str, object] = {}
    for period_type, group in rows.groupby("period_type", sort=True):
        positive = group["positive"].astype(bool).tolist()
        current = 0
        worst = 0
        for value in positive:
            if value:
                current = 0
            else:
                current += 1
                worst = max(worst, current)
        pnl = pd.to_numeric(group["total_net_pnl_bps"], errors="coerce").fillna(0.0)
        output[str(period_type)] = {
            "periods": int(len(group)),
            "positive_periods": int(sum(positive)),
            "positive_rate": float(sum(positive) / len(positive)) if positive else 0.0,
            "worst_period_net_pnl_bps": float(pnl.min()) if len(pnl) else 0.0,
            "max_consecutive_negative_periods": int(worst),
        }
    return output


def _write_report(payload: dict[str, object], delay_summary: pd.DataFrame) -> None:
    decision = payload["decision"]
    signal = payload["delay_stress"]["signal_hour"]["aggregate"]
    entry = payload["delay_stress"]["entry_hour"]["aggregate"]
    period = payload["period_loss_runs"]
    lines = [
        "# Research V71 Fixed Flow Dense Delay Stress Results",
        "",
        "## Decision",
        "",
        f"- V69 retained: `{decision['v69_retained']}`",
        f"- Stronger validation promoted: `{decision['stronger_validation_promoted']}`",
        f"- Failed stricter checks: `{';'.join(decision['failed_stricter_checks'])}`",
        "",
        "## Dense Delay Stress",
        "",
        f"- Delay grid: `0..120` minutes, one-minute resolution",
        f"- Signal-hour gate positive delay rate: `{float(signal['positive_delay_rate']):.6f}`",
        f"- Signal-hour gate worst delay total: `{float(signal['worst_delay_total_net_pnl_bps']):.6f}` bps",
        f"- Entry-hour gate positive delay rate: `{float(entry['positive_delay_rate']):.6f}`",
        f"- Entry-hour gate worst delay total: `{float(entry['worst_delay_total_net_pnl_bps']):.6f}` bps",
        "",
        "## Period Loss Runs",
        "",
        "```json",
        json.dumps(period, indent=2, default=str),
        "```",
        "",
        "## Delay Summary",
        "",
        delay_summary.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V71 does not change the V68 fixed candidate or V69 locked hour gate. It checks whether the same candidate survives a dense 0-120 minute entry-delay grid. V69 remains a research candidate only when the locked gate is used as originally tested; the stricter delay and period checks decide whether it can be promoted to a stronger stability claim.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    v68 = json.loads(V68_SUMMARY.read_text(encoding="utf-8"))
    v69 = json.loads(V69_SUMMARY.read_text(encoding="utf-8"))
    bars = _load_bars(INPUT_BARS)
    base_ledger = pd.read_csv(V68_BASE_LEDGER)
    date_to_fold = _date_to_fold_map(base_ledger)
    candidate = _candidate_from_v68(v68)
    excluded_hours = [int(x) for x in v69["hour_gate"]["excluded_hours"]]

    delayed = build_delayed_candidate_trade_ledger_grid(bars, candidate, entry_delay_minutes=ENTRY_DELAYS)
    delayed.to_csv(OUT_DIR / "v71_dense_delay_raw_ledgers.csv", index=False)

    stress_payload: dict[str, object] = {}
    delay_frames: list[pd.DataFrame] = []
    for gate_mode in ("signal_hour", "entry_hour"):
        gated = _apply_locked_hour_gate(delayed, excluded_hours=excluded_hours, gate_mode=gate_mode, date_to_fold=date_to_fold)
        gated.to_csv(OUT_DIR / f"v71_dense_delay_{gate_mode}_gated_ledgers.csv", index=False)
        summary = summarize_delay_stress_grid(
            gated,
            delay_col="entry_delay_minutes",
            fold_col="fold",
            min_positive_delay_rate=0.80,
            min_worst_delay_total_net_pnl_bps=0.0,
        )
        frame = pd.DataFrame(summary["delays"])
        frame.insert(0, "gate_mode", gate_mode)
        frame.to_csv(OUT_DIR / f"v71_dense_delay_{gate_mode}_summary.csv", index=False)
        delay_frames.append(frame)
        stress_payload[gate_mode] = summary

    delay_summary = pd.concat(delay_frames, ignore_index=True) if delay_frames else pd.DataFrame()
    delay_summary.to_csv(OUT_DIR / "v71_dense_delay_summary.csv", index=False)

    v69_trades = _load_trades(V69_LEDGER)
    period_summary = pd.read_csv(V70_PERIOD_SUMMARY)
    period_loss_runs = _period_loss_run_summary(period_summary)
    v69_total = float(pd.to_numeric(v69_trades["net_pnl_bps"], errors="coerce").fillna(0.0).sum())
    v69_decision = v69["decision"]

    signal_agg = stress_payload["signal_hour"]["aggregate"]
    entry_agg = stress_payload["entry_hour"]["aggregate"]
    stricter_checks = {
        "v69_locked_gate_passed": bool(v69_decision["passed"]),
        "signal_hour_delay_positive_rate_ge_0p80": float(signal_agg["positive_delay_rate"]) >= 0.80,
        "signal_hour_worst_delay_nonnegative": float(signal_agg["worst_delay_total_net_pnl_bps"]) >= 0.0,
        "entry_hour_delay_positive_rate_ge_0p80": float(entry_agg["positive_delay_rate"]) >= 0.80,
        "entry_hour_worst_delay_nonnegative": float(entry_agg["worst_delay_total_net_pnl_bps"]) >= 0.0,
        "month_positive_rate_ge_0p60": float(period_loss_runs["month"]["positive_rate"]) >= 0.60,
        "quarter_positive_rate_ge_0p75": float(period_loss_runs["quarter"]["positive_rate"]) >= 0.75,
    }
    failed = [name for name, passed in stricter_checks.items() if not passed]
    decision = {
        "v69_retained": bool(v69_decision["passed"] and v69_total > 0.0),
        "stronger_validation_promoted": bool(not failed),
        "stricter_checks": stricter_checks,
        "failed_stricter_checks": failed,
        "v69_total_net_pnl_bps": v69_total,
        "delay_grid_min_minutes": int(min(ENTRY_DELAYS)),
        "delay_grid_max_minutes": int(max(ENTRY_DELAYS)),
        "delay_grid_count": int(len(ENTRY_DELAYS)),
    }
    payload = {
        "version": "v71_btcusdc_fixed_flow_dense_delay_stress",
        "source_v68_summary": str(V68_SUMMARY),
        "source_v69_summary": str(V69_SUMMARY),
        "candidate": candidate.to_dict(),
        "excluded_hours": excluded_hours,
        "decision": decision,
        "delay_stress": stress_payload,
        "period_loss_runs": period_loss_runs,
        "outputs": {
            "summary_json": str(OUT_DIR / "v71_summary.json"),
            "dense_delay_summary": str(OUT_DIR / "v71_dense_delay_summary.csv"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v71_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, delay_summary)
    print(json.dumps(payload, indent=2, default=str))
