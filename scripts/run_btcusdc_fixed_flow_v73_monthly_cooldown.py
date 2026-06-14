from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import summarize_monthly_loss_cooldown


ROOT = Path(__file__).resolve().parents[1]
V69_LEDGER = ROOT / "runs" / "research_v69_btcusdc_fixed_flow_hour_gate" / "v69_hour_gated_trade_ledger.csv"
V72_SUMMARY = ROOT / "runs" / "research_v72_btcusdc_fixed_flow_cost_delay_contract" / "v72_summary.json"
OUT_DIR = ROOT / "runs" / "research_v73_btcusdc_fixed_flow_monthly_cooldown"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V73_FIXED_FLOW_MONTHLY_COOLDOWN_RESULTS.md"

DESIGN_FOLDS = (1, 2, 3, 4)
HOLDOUT_FOLDS = (5, 6, 7)
POLICIES = tuple((trigger, cooldown) for trigger in (1, 2, 3) for cooldown in (1, 2, 3))


def _load_trades(path: Path) -> pd.DataFrame:
    trades = pd.read_csv(path)
    trades["timestamp"] = pd.to_datetime(trades["timestamp"], utc=True)
    trades["net_pnl_bps"] = pd.to_numeric(trades["net_pnl_bps"], errors="coerce").fillna(0.0)
    trades["fold"] = pd.to_numeric(trades["fold"], errors="coerce").astype("Int64")
    trades["month"] = trades["timestamp"].dt.tz_convert(None).dt.to_period("M").astype(str)
    return trades.dropna(subset=["fold"]).sort_values("timestamp").reset_index(drop=True)


def _period_baseline(trades: pd.DataFrame) -> dict[str, object]:
    month_totals = trades.groupby("month", sort=True)["net_pnl_bps"].sum()
    values = [float(x) for x in month_totals.tolist()]
    return {
        "months": int(len(values)),
        "trades": int(len(trades)),
        "total_net_pnl_bps": float(sum(values)),
        "positive_month_rate": float(sum(value > 0.0 for value in values) / len(values)) if values else 0.0,
        "worst_month_net_pnl_bps": float(min(values)) if values else 0.0,
    }


def _scan_design_policies(design_trades: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for trigger, cooldown in POLICIES:
        result = summarize_monthly_loss_cooldown(design_trades, trigger_negative_months=trigger, cooldown_months=cooldown)
        agg = result["aggregate"]
        rows.append(
            {
                "trigger_negative_months": int(trigger),
                "cooldown_months": int(cooldown),
                "design_trades": int(agg["trades"]),
                "design_skipped_trades": int(agg["skipped_trades"]),
                "design_total_net_pnl_bps": float(agg["total_net_pnl_bps"]),
                "design_positive_month_rate": float(agg["positive_month_rate"]),
                "design_worst_month_net_pnl_bps": float(agg["worst_month_net_pnl_bps"]),
                "design_risk_off_months": int(agg["risk_off_months"]),
            }
        )
    frame = pd.DataFrame(rows)
    return frame.sort_values(
        [
            "design_positive_month_rate",
            "design_total_net_pnl_bps",
            "design_worst_month_net_pnl_bps",
            "trigger_negative_months",
            "cooldown_months",
        ],
        ascending=[False, False, False, True, True],
    ).reset_index(drop=True)


def _filter_kept_trades(trades: pd.DataFrame, month_rows: pd.DataFrame) -> pd.DataFrame:
    risk_off_months = set(month_rows.loc[month_rows["risk_off"].astype(bool), "month"].astype(str).tolist())
    return trades.loc[~trades["month"].astype(str).isin(risk_off_months)].copy().reset_index(drop=True)


def _fold_summary(trades: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for fold, group in trades.groupby("fold", sort=True):
        pnl = pd.to_numeric(group["net_pnl_bps"], errors="coerce").fillna(0.0)
        rows.append(
            {
                "fold": int(fold),
                "trades": int(len(group)),
                "total_net_pnl_bps": float(pnl.sum()),
                "positive": bool(float(pnl.sum()) > 0.0),
            }
        )
    return pd.DataFrame(rows)


def _write_report(payload: dict[str, object], design_scan: pd.DataFrame, month_rows: pd.DataFrame, fold_rows: pd.DataFrame) -> None:
    decision = payload["decision"]
    selected = payload["selected_policy"]
    baseline = payload["baseline"]
    selected_full = payload["selected_full"]
    lines = [
        "# Research V73 Fixed Flow Monthly Cooldown Results",
        "",
        "## Decision",
        "",
        f"- Monthly cooldown promoted: `{decision['monthly_cooldown_promoted']}`",
        f"- Stronger validation promoted: `{decision['stronger_validation_promoted']}`",
        f"- Failed checks: `{';'.join(decision['failed_checks'])}`",
        "",
        "## Selected Policy",
        "",
        f"- Trigger negative months: `{selected['trigger_negative_months']}`",
        f"- Cooldown months: `{selected['cooldown_months']}`",
        "",
        "## Baseline vs Selected",
        "",
        f"- Baseline total: `{float(baseline['total_net_pnl_bps']):.6f}` bps",
        f"- Baseline positive month rate: `{float(baseline['positive_month_rate']):.6f}`",
        f"- Selected total: `{float(selected_full['total_net_pnl_bps']):.6f}` bps",
        f"- Selected positive month rate: `{float(selected_full['positive_month_rate']):.6f}`",
        f"- Selected skipped trades: `{selected_full['skipped_trades']}`",
        "",
        "## Design Scan",
        "",
        design_scan.to_csv(index=False).strip(),
        "",
        "## Selected Month Rows",
        "",
        month_rows.to_csv(index=False).strip(),
        "",
        "## Selected Fold Rows",
        "",
        fold_rows.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V73 tests a causal monthly cooldown. The cooldown policy is selected using design folds only, then evaluated on the full ledger and holdout folds. A policy is not promoted unless it improves month stability without breaking holdout profitability.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    trades = _load_trades(V69_LEDGER)
    v72 = json.loads(V72_SUMMARY.read_text(encoding="utf-8"))
    design = trades.loc[trades["fold"].astype(int).isin(DESIGN_FOLDS)].copy()
    baseline = _period_baseline(trades)
    baseline_design = _period_baseline(design)
    design_scan = _scan_design_policies(design)
    selected_row = design_scan.iloc[0]
    trigger = int(selected_row["trigger_negative_months"])
    cooldown = int(selected_row["cooldown_months"])

    selected_result = summarize_monthly_loss_cooldown(trades, trigger_negative_months=trigger, cooldown_months=cooldown)
    month_rows = pd.DataFrame(selected_result["months"])
    kept_trades = _filter_kept_trades(trades, month_rows)
    kept_trades.to_csv(OUT_DIR / "v73_selected_kept_trade_ledger.csv", index=False)
    month_rows.to_csv(OUT_DIR / "v73_selected_month_rows.csv", index=False)
    design_scan.to_csv(OUT_DIR / "v73_design_policy_scan.csv", index=False)
    fold_rows = _fold_summary(kept_trades)
    fold_rows.to_csv(OUT_DIR / "v73_selected_fold_rows.csv", index=False)

    holdout = kept_trades.loc[kept_trades["fold"].astype(int).isin(HOLDOUT_FOLDS)].copy()
    holdout_folds = _fold_summary(holdout)
    holdout_totals = pd.to_numeric(holdout_folds.get("total_net_pnl_bps", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    selected_full = selected_result["aggregate"]
    checks = {
        "selected_design_positive_month_rate_ge_baseline": float(selected_row["design_positive_month_rate"]) >= float(baseline_design["positive_month_rate"]),
        "selected_full_positive_month_rate_ge_0p60": float(selected_full["positive_month_rate"]) >= 0.60,
        "selected_total_net_pnl_positive": float(selected_full["total_net_pnl_bps"]) > 0.0,
        "selected_total_ge_baseline": float(selected_full["total_net_pnl_bps"]) >= float(baseline["total_net_pnl_bps"]),
        "holdout_total_positive": float(holdout_totals.sum()) > 0.0,
        "holdout_all_active_folds_positive": bool(len(holdout_totals) == len(HOLDOUT_FOLDS) and (holdout_totals > 0.0).all()),
        "v72_execution_contract_found": bool(v72["decision"]["execution_contract_found"]),
    }
    failed = [name for name, passed in checks.items() if not passed]
    promoted = bool(not failed)
    payload = {
        "version": "v73_btcusdc_fixed_flow_monthly_cooldown",
        "source_v69_ledger": str(V69_LEDGER),
        "source_v72_summary": str(V72_SUMMARY),
        "design_folds": list(DESIGN_FOLDS),
        "holdout_folds": list(HOLDOUT_FOLDS),
        "baseline": baseline,
        "baseline_design": baseline_design,
        "selected_policy": {
            "trigger_negative_months": trigger,
            "cooldown_months": cooldown,
            "design_total_net_pnl_bps": float(selected_row["design_total_net_pnl_bps"]),
            "design_positive_month_rate": float(selected_row["design_positive_month_rate"]),
            "design_worst_month_net_pnl_bps": float(selected_row["design_worst_month_net_pnl_bps"]),
        },
        "selected_full": selected_full,
        "holdout": {
            "trades": int(len(holdout)),
            "total_net_pnl_bps": float(holdout_totals.sum()) if len(holdout_totals) else 0.0,
            "positive_fold_rate": float((holdout_totals > 0.0).mean()) if len(holdout_totals) else 0.0,
            "active_folds": int(len(holdout_totals)),
        },
        "decision": {
            "monthly_cooldown_promoted": promoted,
            "stronger_validation_promoted": promoted,
            "checks": checks,
            "failed_checks": failed,
        },
        "outputs": {
            "summary_json": str(OUT_DIR / "v73_summary.json"),
            "design_policy_scan": str(OUT_DIR / "v73_design_policy_scan.csv"),
            "selected_month_rows": str(OUT_DIR / "v73_selected_month_rows.csv"),
            "selected_fold_rows": str(OUT_DIR / "v73_selected_fold_rows.csv"),
            "selected_kept_trade_ledger": str(OUT_DIR / "v73_selected_kept_trade_ledger.csv"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v73_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, design_scan, month_rows, fold_rows)
    print(json.dumps(payload, indent=2, default=str))
