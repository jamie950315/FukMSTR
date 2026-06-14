from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import summarize_holdout_failure_attribution


ROOT = Path(__file__).resolve().parents[1]
V75_SUMMARY = ROOT / "runs" / "research_v75_btcusdc_fixed_flow_design_selected_combined_policy" / "v75_summary.json"
V75_SELECTED_LEDGER = ROOT / "runs" / "research_v75_btcusdc_fixed_flow_design_selected_combined_policy" / "v75_selected_kept_trade_ledger.csv"
OUT_DIR = ROOT / "runs" / "research_v76_btcusdc_fixed_flow_holdout_failure_attribution"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V76_FIXED_FLOW_HOLDOUT_FAILURE_ATTRIBUTION_RESULTS.md"


def _load_ledger(path: Path) -> pd.DataFrame:
    trades = pd.read_csv(path)
    trades["timestamp"] = pd.to_datetime(trades["timestamp"], utc=True)
    trades["fold"] = pd.to_numeric(trades["fold"], errors="coerce").astype("Int64")
    trades["entry_delay_minutes"] = pd.to_numeric(trades["entry_delay_minutes"], errors="coerce").astype("Int64")
    trades["net_pnl_bps"] = pd.to_numeric(trades["net_pnl_bps"], errors="coerce").fillna(0.0)
    return trades.dropna(subset=["timestamp", "fold", "entry_delay_minutes"]).reset_index(drop=True)


def _frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _top_loss(rows: list[dict[str, object]], key: str) -> dict[str, object] | None:
    negatives = [row for row in rows if float(row["total_net_pnl_bps"]) < 0.0]
    if not negatives:
        return None
    return min(negatives, key=lambda row: float(row["total_net_pnl_bps"]))


def _write_report(payload: dict[str, object], result: dict[str, object]) -> None:
    decision = payload["decision"]
    agg = result["aggregate"]
    lines = [
        "# Research V76 Fixed Flow Holdout Failure Attribution Results",
        "",
        "## Decision",
        "",
        f"- Diagnostic completed: `{decision['diagnostic_completed']}`",
        f"- Stronger validation promoted: `{decision['stronger_validation_promoted']}`",
        f"- Failed checks carried from V75: `{';'.join(decision['v75_failed_checks'])}`",
        "",
        "## Scope",
        "",
        "V76 explains the V75 holdout failure using the selected V75 kept ledger under the V72 execution contract. The ledger contains all delay scenarios from 0 to 60 minutes, so totals are stress-grid attribution totals, not a single live account curve.",
        "",
        "## Aggregate",
        "",
        f"- Holdout trades in stress grid: `{agg['holdout_trades']}`",
        f"- Holdout total: `{float(agg['holdout_total_net_pnl_bps']):.6f}` bps",
        f"- Negative folds: `{agg['negative_fold_count']}`",
        f"- Negative months: `{agg['negative_month_count']}`",
        f"- Negative UTC hours: `{agg['negative_hour_count']}`",
        f"- Negative delays: `{agg['negative_delay_count']}`",
        f"- Worst fold: `{float(agg['worst_fold_net_pnl_bps']):.6f}` bps",
        f"- Worst month: `{float(agg['worst_month_net_pnl_bps']):.6f}` bps",
        f"- Worst UTC hour: `{float(agg['worst_hour_net_pnl_bps']):.6f}` bps",
        f"- Worst delay: `{float(agg['worst_delay_net_pnl_bps']):.6f}` bps",
        "",
        "## Top Loss Buckets",
        "",
        _frame(payload["top_loss_buckets"]).to_csv(index=False).strip(),
        "",
        "## By Fold",
        "",
        _frame(result["by_fold"]).to_csv(index=False).strip(),
        "",
        "## By Month",
        "",
        _frame(result["by_month"]).head(20).to_csv(index=False).strip(),
        "",
        "## By UTC Hour",
        "",
        _frame(result["by_hour"]).to_csv(index=False).strip(),
        "",
        "## By Delay",
        "",
        _frame(result["by_delay"]).head(20).to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "The loss is not solved by the design-selected monthly cooldown path. V76 checks whether the V75 holdout failure is concentrated enough to justify a future, predeclared diagnostic branch; it does not change thresholds or promote a stronger contract.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    v75 = json.loads(V75_SUMMARY.read_text(encoding="utf-8"))
    holdout_folds = [int(x) for x in v75["holdout_folds"]]
    trades = _load_ledger(V75_SELECTED_LEDGER)
    result = summarize_holdout_failure_attribution(trades, holdout_folds=holdout_folds)

    by_fold = _frame(result["by_fold"])
    by_month = _frame(result["by_month"])
    by_hour = _frame(result["by_hour"])
    by_delay = _frame(result["by_delay"])

    by_fold.to_csv(OUT_DIR / "v76_by_fold.csv", index=False)
    by_month.to_csv(OUT_DIR / "v76_by_month.csv", index=False)
    by_hour.to_csv(OUT_DIR / "v76_by_utc_hour.csv", index=False)
    by_delay.to_csv(OUT_DIR / "v76_by_delay.csv", index=False)

    top_loss_buckets: list[dict[str, object]] = []
    for label, rows, key in [
        ("fold", result["by_fold"], "fold"),
        ("month", result["by_month"], "month"),
        ("utc_hour", result["by_hour"], "hour"),
        ("delay", result["by_delay"], "entry_delay_minutes"),
    ]:
        top = _top_loss(rows, key)
        if top is not None:
            top_loss_buckets.append(
                {
                    "bucket_type": label,
                    "bucket": top[key],
                    "trades": int(top["trades"]),
                    "total_net_pnl_bps": float(top["total_net_pnl_bps"]),
                    "negative_loss_share": float(top["negative_loss_share"]),
                }
            )

    payload = {
        "version": "v76_btcusdc_fixed_flow_holdout_failure_attribution",
        "source_v75_summary": str(V75_SUMMARY),
        "source_v75_selected_ledger": str(V75_SELECTED_LEDGER),
        "holdout_folds": holdout_folds,
        "contract": v75["contract"],
        "selected_policy": v75["selected_policy"],
        "attribution": {"aggregate": result["aggregate"]},
        "top_loss_buckets": top_loss_buckets,
        "decision": {
            "diagnostic_completed": True,
            "stronger_validation_promoted": False,
            "v75_failed_checks": v75["decision"]["failed_checks"],
        },
        "outputs": {
            "summary_json": str(OUT_DIR / "v76_summary.json"),
            "by_fold": str(OUT_DIR / "v76_by_fold.csv"),
            "by_month": str(OUT_DIR / "v76_by_month.csv"),
            "by_utc_hour": str(OUT_DIR / "v76_by_utc_hour.csv"),
            "by_delay": str(OUT_DIR / "v76_by_delay.csv"),
            "report": str(REPORT_PATH),
        },
    }

    (OUT_DIR / "v76_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, result)
    print(json.dumps(payload, indent=2, default=str))
