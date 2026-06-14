from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import summarize_short_term_candidate_validation


ROOT = Path(__file__).resolve().parents[1]
V69_DIR = ROOT / "runs" / "research_v69_btcusdc_fixed_flow_hour_gate"
OUT_DIR = ROOT / "runs" / "research_v86_btcusdc_short_term_recent_validation"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V86_BTCUSDC_SHORT_TERM_RECENT_VALIDATION_RESULTS.md"

INPUT_LEDGER = V69_DIR / "v69_hour_gated_trade_ledger.csv"
DELAY_SUMMARY = V69_DIR / "v69_delay_summary.csv"
EXTRA_COST_SUMMARY = V69_DIR / "v69_extra_cost_summary.csv"

HOLDOUT_FOLDS = (5, 6, 7)
RECENT_MONTHS = 6
RECENT_TAIL_ACTIVE_MONTHS = 3
WINDOWS = {
    "UTC 00-04": (0, 1, 2, 3, 4),
    "UTC 06-11": (6, 7, 8, 9, 10, 11),
    "UTC 13": (13,),
    "UTC 15": (15,),
    "UTC 17-19": (17, 18, 19),
    "UTC 21-22": (21, 22),
    "V69 all kept hours": (0, 1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 13, 15, 17, 18, 19, 21, 22),
}


def _window_stats(trades: pd.DataFrame) -> pd.DataFrame:
    frame = trades.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["hour"] = frame["timestamp"].dt.hour.astype(int)
    frame["fold"] = pd.to_numeric(frame["fold"], errors="coerce").astype("Int64")
    frame["net_pnl_bps"] = pd.to_numeric(frame["net_pnl_bps"], errors="coerce").fillna(0.0)
    rows: list[dict[str, object]] = []
    for name, hours in WINDOWS.items():
        group = frame.loc[frame["hour"].isin([int(hour) for hour in hours])].copy()
        pnl = pd.to_numeric(group["net_pnl_bps"], errors="coerce").fillna(0.0)
        fold_totals = group.groupby("fold", sort=True)["net_pnl_bps"].sum()
        rows.append(
            {
                "window": name,
                "hours": ",".join(str(hour) for hour in hours),
                "trades": int(len(group)),
                "total_net_pnl_bps": float(pnl.sum()),
                "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                "win_rate": float((pnl > 0.0).mean()) if len(pnl) else 0.0,
                "active_folds": int(len(fold_totals)),
                "positive_fold_rate": float((fold_totals > 0.0).mean()) if len(fold_totals) else 0.0,
                "worst_fold_net_pnl_bps": float(fold_totals.min()) if len(fold_totals) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _month_stats(trades: pd.DataFrame) -> pd.DataFrame:
    frame = trades.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["month"] = frame["timestamp"].dt.tz_convert(None).dt.to_period("M")
    frame["net_pnl_bps"] = pd.to_numeric(frame["net_pnl_bps"], errors="coerce").fillna(0.0)
    totals = frame.groupby("month", sort=True)["net_pnl_bps"].sum()
    rows = [
        {
            "month": str(month),
            "total_net_pnl_bps": float(total),
            "positive": bool(total > 0.0),
        }
        for month, total in totals.items()
    ]
    return pd.DataFrame(rows)


def _write_report(payload: dict[str, object], windows: pd.DataFrame, months: pd.DataFrame) -> None:
    short_term = payload["short_term"]
    recent = payload["recent"]
    decision = payload["decision"]
    lines = [
        "# Research V86 BTCUSDC Short-Term Recent Validation Results",
        "",
        "## Decision",
        "",
        f"- Short-term candidate passed: `{decision['short_term_candidate_passed']}`",
        f"- Recent edge valid: `{decision['recent_edge_valid']}`",
        f"- Promote short-term candidate: `{decision['promote_short_term_candidate']}`",
        f"- Next action: `{decision['next_action']}`",
        "",
        "## 12h Short-Term Gate",
        "",
        f"- Trades: `{short_term['trade_count']}`",
        f"- Total net PnL: `{float(short_term['total_net_pnl_bps']):.6f}` bps",
        f"- Mean net PnL: `{float(short_term['mean_net_pnl_bps']):.6f}` bps",
        f"- Win rate: `{float(short_term['win_rate']):.6f}`",
        f"- Positive fold rate: `{float(short_term['positive_fold_rate']):.6f}`",
        f"- Worst fold: `{float(short_term['worst_fold_net_pnl_bps']):.6f}` bps",
        f"- Holdout total: `{float(short_term['holdout_total_net_pnl_bps']):.6f}` bps",
        f"- Holdout positive fold rate: `{float(short_term['holdout_positive_fold_rate']):.6f}`",
        f"- Worst delay total: `{float(short_term['worst_delay_total_net_pnl_bps']):.6f}` bps",
        f"- Required extra cost total at +{float(short_term['required_extra_cost_bps']):.1f} bps: `{float(short_term['required_extra_cost_total_net_pnl_bps']):.6f}` bps",
        f"- Failed checks: `{';'.join(short_term['failed_checks'])}`",
        "",
        "## Recent Edge Gate",
        "",
        f"- Recent months: `{recent['recent_months']}`",
        f"- Recent total net PnL: `{float(recent['recent_total_net_pnl_bps']):.6f}` bps",
        f"- Recent calendar positive month rate: `{float(recent['recent_calendar_positive_month_rate']):.6f}`",
        f"- Recent active month count: `{recent['recent_active_month_count']}`",
        f"- Recent active positive month rate: `{float(recent['recent_active_positive_month_rate']):.6f}`",
        f"- Tail active month count: `{recent['tail_active_month_count']}`",
        f"- Tail active total net PnL: `{float(recent['tail_active_total_net_pnl_bps']):.6f}` bps",
        f"- Tail active positive month rate: `{float(recent['tail_active_positive_month_rate']):.6f}`",
        f"- Latest active month: `{recent['latest_active_month']}`",
        f"- Latest active month net PnL: `{float(recent['latest_active_month_net_pnl_bps']):.6f}` bps",
        f"- Failed checks: `{';'.join(recent['failed_checks'])}`",
        "",
        "## Time Windows",
        "",
        windows.to_csv(index=False).strip(),
        "",
        "## Monthly Results",
        "",
        months.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V86 reframes V69 as a 12-hour short-term BTCUSDC research candidate instead of an all-day strategy route. Under that narrower short-term gate, the V69 candidate still passes: it has positive total PnL, positive holdout folds, positive tested delay totals, and remains positive under the +16 bps extra-cost stress.",
        "",
        "The recent-edge gate does not pass. The last six calendar months are still net positive, but the latest active month is negative and only one of the last three active months is positive. This keeps the candidate in research/monitoring status rather than promotion status.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    if not INPUT_LEDGER.exists():
        raise SystemExit(f"missing input ledger: {INPUT_LEDGER}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    trades = pd.read_csv(INPUT_LEDGER)
    delay_summary = pd.read_csv(DELAY_SUMMARY)
    extra_cost_summary = pd.read_csv(EXTRA_COST_SUMMARY)
    result = summarize_short_term_candidate_validation(
        trades,
        delay_summary=delay_summary,
        extra_cost_summary=extra_cost_summary,
        holdout_folds=HOLDOUT_FOLDS,
        recent_months=RECENT_MONTHS,
        recent_tail_active_months=RECENT_TAIL_ACTIVE_MONTHS,
    )
    windows = _window_stats(trades)
    months = _month_stats(trades)
    windows.to_csv(OUT_DIR / "v86_time_windows.csv", index=False)
    months.to_csv(OUT_DIR / "v86_months.csv", index=False)
    payload = {
        "version": "v86_btcusdc_short_term_recent_validation",
        "input_ledger": str(INPUT_LEDGER),
        "source_candidate": "V69 fixed-flow design-only hour gate",
        **result,
        "outputs": {
            "summary_json": str(OUT_DIR / "v86_summary.json"),
            "time_windows": str(OUT_DIR / "v86_time_windows.csv"),
            "months": str(OUT_DIR / "v86_months.csv"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v86_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, windows, months)
    print(json.dumps(payload, indent=2, default=str))
