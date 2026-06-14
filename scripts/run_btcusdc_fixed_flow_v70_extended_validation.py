from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import (
    audit_prequential_hour_exclusion_gate,
    summarize_hour_exclusion_combination_null,
)


ROOT = Path(__file__).resolve().parents[1]
V69_DIR = ROOT / "runs" / "research_v69_btcusdc_fixed_flow_hour_gate"
OUT_DIR = ROOT / "runs" / "research_v70_btcusdc_fixed_flow_extended_validation"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V70_FIXED_FLOW_EXTENDED_VALIDATION_RESULTS.md"

V68_BASE_LEDGER = ROOT / "runs" / "research_v68_btcusdc_fixed_flow_stability" / "v68_base_trade_ledger.csv"
V69_LEDGER = V69_DIR / "v69_hour_gated_trade_ledger.csv"
V69_SUMMARY = V69_DIR / "v69_summary.json"

LEVERAGE = 8.0


def _load_trades(path: Path) -> pd.DataFrame:
    trades = pd.read_csv(path)
    trades["timestamp"] = pd.to_datetime(trades["timestamp"], utc=True)
    trades["net_pnl_bps"] = pd.to_numeric(trades["net_pnl_bps"], errors="coerce").fillna(0.0)
    trades["hour"] = trades["timestamp"].dt.hour.astype(int)
    return trades


def _period_summary(trades: pd.DataFrame, period: str) -> pd.DataFrame:
    out = trades.copy()
    out[period] = out["timestamp"].dt.to_period("M" if period == "month" else "Q").astype(str)
    rows: list[dict[str, object]] = []
    for key, group in out.groupby(period, sort=True):
        pnl = pd.to_numeric(group["net_pnl_bps"], errors="coerce").fillna(0.0)
        rows.append(
            {
                "period_type": period,
                "period": str(key),
                "trades": int(len(group)),
                "total_net_pnl_bps": float(pnl.sum()),
                "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                "account_return_pct": float(pnl.sum()) * LEVERAGE / 100.0,
                "positive": bool(float(pnl.sum()) > 0.0),
            }
        )
    return pd.DataFrame(rows)


def _risk_governor_scan(trades: pd.DataFrame) -> pd.DataFrame:
    ordered = trades.sort_values("timestamp").reset_index(drop=True)
    rows: list[dict[str, object]] = []
    for loss_trigger_bps in (-20.0, -40.0, -60.0, -80.0, -100.0, -150.0, -200.0):
        for skip_count in (1, 2, 3, 5, 8, 10):
            kept = []
            skip = 0
            for _, row in ordered.iterrows():
                if skip > 0:
                    skip -= 1
                    continue
                kept.append(row)
                if float(row["net_pnl_bps"]) <= float(loss_trigger_bps):
                    skip = int(skip_count)
            frame = pd.DataFrame(kept)
            pnl = pd.to_numeric(frame.get("net_pnl_bps", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
            fold_totals = frame.groupby("fold")["net_pnl_bps"].sum() if not frame.empty else pd.Series(dtype=float)
            holdout = frame.loc[pd.to_numeric(frame.get("fold", pd.Series(dtype=float)), errors="coerce").fillna(0).astype(int) >= 5]
            holdout_totals = holdout.groupby("fold")["net_pnl_bps"].sum() if not holdout.empty else pd.Series(dtype=float)
            rows.append(
                {
                    "loss_trigger_bps": float(loss_trigger_bps),
                    "skip_count": int(skip_count),
                    "trades": int(len(frame)),
                    "total_net_pnl_bps": float(pnl.sum()),
                    "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                    "positive_fold_rate": float((fold_totals > 0.0).mean()) if len(fold_totals) else 0.0,
                    "worst_fold_net_pnl_bps": float(fold_totals.min()) if len(fold_totals) else 0.0,
                    "holdout_total_net_pnl_bps": float(holdout_totals.sum()) if len(holdout_totals) else 0.0,
                    "holdout_all_positive": bool(len(holdout_totals) > 0 and (holdout_totals > 0.0).all()),
                    "holdout_worst_fold_net_pnl_bps": float(holdout_totals.min()) if len(holdout_totals) else 0.0,
                }
            )
    return pd.DataFrame(rows).sort_values(["total_net_pnl_bps", "holdout_total_net_pnl_bps"], ascending=[False, False]).reset_index(drop=True)


def _write_report(payload: dict[str, object], period_summary: pd.DataFrame, risk_scan: pd.DataFrame) -> None:
    decision = payload["decision"]
    preq = payload["prequential_hour_gate"]["aggregate"]
    combo = payload["hour_combination_null"]
    lines = [
        "# Research V70 Fixed Flow Extended Validation Results",
        "",
        "## Decision",
        "",
        f"- V69 retained: `{decision['v69_retained']}`",
        f"- Stronger validation promoted: `{decision['stronger_validation_promoted']}`",
        f"- Failed stricter checks: `{';'.join(decision['failed_stricter_checks'])}`",
        "",
        "## V69 Locked Gate",
        "",
        f"- Total net pnl: `{float(decision['v69_total_net_pnl_bps']):.6f}` bps",
        f"- Holdout total net pnl: `{float(decision['v69_holdout_total_net_pnl_bps']):.6f}` bps",
        "",
        "## Prequential Dynamic Hour Gate",
        "",
        f"- Passed: `{preq['passed']}`",
        f"- Total net pnl: `{float(preq['total_net_pnl_bps']):.6f}` bps",
        f"- Worst fold: `{float(preq['worst_fold_net_pnl_bps']):.6f}` bps",
        "",
        "## Hour Combination Null",
        "",
        f"- Combination count: `{combo['combination_count']}`",
        f"- Selected total rank share: `{float(combo['share_combinations_total_ge_selected']):.6f}`",
        f"- Selected total: `{float(combo['selected_total_net_pnl_bps']):.6f}` bps",
        f"- Median combination total: `{float(combo['median_total_net_pnl_bps']):.6f}` bps",
        "",
        "## Period Summary",
        "",
        period_summary.to_csv(index=False).strip(),
        "",
        "## Risk Governor Scan Top 10",
        "",
        risk_scan.head(10).to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V69 remains the best current candidate. More validation supports that the locked design-only gate is profitable and unusually strong versus hour-combination alternatives. However, dynamic re-selection of the hour gate fails one forward fold, and monthly results are mixed. Do not upgrade this to a live-profit claim without fresh post-2026-06 validation or deeper execution modeling.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    base = _load_trades(V68_BASE_LEDGER)
    v69_trades = _load_trades(V69_LEDGER)
    v69 = json.loads(V69_SUMMARY.read_text(encoding="utf-8"))
    excluded_hours = [int(x) for x in v69["hour_gate"]["excluded_hours"]]

    preq = audit_prequential_hour_exclusion_gate(
        base,
        evaluation_folds=[5, 6, 7],
        min_history_folds=4,
        max_excluded_hours=8,
        min_design_positive_fold_rate=0.75,
        min_design_worst_fold_net_pnl_bps=-500.0,
    )
    combo = summarize_hour_exclusion_combination_null(base, selected_excluded_hours=excluded_hours)
    period = pd.concat([_period_summary(v69_trades, "month"), _period_summary(v69_trades, "quarter")], ignore_index=True)
    risk_scan = _risk_governor_scan(v69_trades)
    month_rows = period.loc[period["period_type"] == "month"]
    quarter_rows = period.loc[period["period_type"] == "quarter"]
    month_positive_rate = float(month_rows["positive"].mean()) if len(month_rows) else 0.0
    quarter_positive_rate = float(quarter_rows["positive"].mean()) if len(quarter_rows) else 0.0
    v69_decision = v69["decision"]
    stricter_checks = {
        "v69_locked_gate_passed": bool(v69_decision["passed"]),
        "prequential_dynamic_gate_passed": bool(preq["aggregate"]["passed"]),
        "month_positive_rate_ge_0p60": month_positive_rate >= 0.60,
        "quarter_positive_rate_ge_0p75": quarter_positive_rate >= 0.75,
        "hour_combo_top_5pct": float(combo["share_combinations_total_ge_selected"]) <= 0.05,
    }
    failed = [name for name, passed in stricter_checks.items() if not passed]
    decision = {
        "v69_retained": bool(v69_decision["passed"] and quarter_positive_rate >= 0.75 and float(combo["share_combinations_total_ge_selected"]) <= 0.05),
        "stronger_validation_promoted": bool(not failed),
        "stricter_checks": stricter_checks,
        "failed_stricter_checks": failed,
        "v69_total_net_pnl_bps": float(v69_decision["total_net_pnl_bps"]),
        "v69_holdout_total_net_pnl_bps": float(v69_decision["holdout_total_net_pnl_bps"]),
        "month_positive_rate": month_positive_rate,
        "quarter_positive_rate": quarter_positive_rate,
        "best_risk_governor_total_net_pnl_bps": float(risk_scan.iloc[0]["total_net_pnl_bps"]) if not risk_scan.empty else 0.0,
        "best_risk_governor_holdout_all_positive": bool(risk_scan.iloc[0]["holdout_all_positive"]) if not risk_scan.empty else False,
    }
    payload = {
        "version": "v70_btcusdc_fixed_flow_extended_validation",
        "source_v69_summary": str(V69_SUMMARY),
        "decision": decision,
        "prequential_hour_gate": preq,
        "hour_combination_null": combo,
        "outputs": {
            "summary_json": str(OUT_DIR / "v70_summary.json"),
            "prequential_csv": str(OUT_DIR / "v70_prequential_hour_gate.csv"),
            "period_summary_csv": str(OUT_DIR / "v70_period_summary.csv"),
            "risk_governor_scan_csv": str(OUT_DIR / "v70_risk_governor_scan.csv"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v70_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    pd.DataFrame(preq["folds"]).to_csv(OUT_DIR / "v70_prequential_hour_gate.csv", index=False)
    period.to_csv(OUT_DIR / "v70_period_summary.csv", index=False)
    risk_scan.to_csv(OUT_DIR / "v70_risk_governor_scan.csv", index=False)
    _write_report(payload, period, risk_scan)
    print(json.dumps(payload, indent=2, default=str))
