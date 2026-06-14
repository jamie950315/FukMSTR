from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import (
    select_delay_monthly_cooldown_policy,
    summarize_delay_monthly_cooldown_grid,
)


ROOT = Path(__file__).resolve().parents[1]
V71_SIGNAL_LEDGER = ROOT / "runs" / "research_v71_btcusdc_fixed_flow_dense_delay_stress" / "v71_dense_delay_signal_hour_gated_ledgers.csv"
V72_SUMMARY = ROOT / "runs" / "research_v72_btcusdc_fixed_flow_cost_delay_contract" / "v72_summary.json"
OUT_DIR = ROOT / "runs" / "research_v75_btcusdc_fixed_flow_design_selected_combined_policy"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V75_FIXED_FLOW_DESIGN_SELECTED_COMBINED_POLICY_RESULTS.md"

DESIGN_FOLDS = (1, 2, 3, 4)
HOLDOUT_FOLDS = (5, 6, 7)
POLICIES = tuple((trigger, cooldown) for trigger in (1, 2, 3) for cooldown in (0, 1, 2, 3))


def _load_trades(path: Path) -> pd.DataFrame:
    trades = pd.read_csv(path)
    trades["timestamp"] = pd.to_datetime(trades["timestamp"], utc=True)
    trades["net_pnl_bps"] = pd.to_numeric(trades["net_pnl_bps"], errors="coerce").fillna(0.0)
    trades["entry_delay_minutes"] = pd.to_numeric(trades["entry_delay_minutes"], errors="coerce").astype("Int64")
    trades["fold"] = pd.to_numeric(trades["fold"], errors="coerce").astype("Int64")
    return trades.dropna(subset=["entry_delay_minutes", "fold"]).sort_values("timestamp").reset_index(drop=True)


def _scan_policies(
    trades: pd.DataFrame,
    *,
    max_delay_minutes: int,
    extra_cost_bps: float,
) -> tuple[pd.DataFrame, dict[tuple[int, int], dict[str, object]]]:
    design = trades.loc[trades["fold"].astype(int).isin(DESIGN_FOLDS)].copy()
    holdout = trades.loc[trades["fold"].astype(int).isin(HOLDOUT_FOLDS)].copy()
    rows: list[dict[str, object]] = []
    results: dict[tuple[int, int], dict[str, object]] = {}
    for trigger, cooldown in POLICIES:
        design_result = summarize_delay_monthly_cooldown_grid(
            design,
            extra_cost_bps=extra_cost_bps,
            max_delay_minutes=max_delay_minutes,
            trigger_negative_months=trigger,
            cooldown_months=cooldown,
        )
        full_result = summarize_delay_monthly_cooldown_grid(
            trades,
            extra_cost_bps=extra_cost_bps,
            max_delay_minutes=max_delay_minutes,
            trigger_negative_months=trigger,
            cooldown_months=cooldown,
            holdout_folds=HOLDOUT_FOLDS,
        )
        holdout_result = summarize_delay_monthly_cooldown_grid(
            holdout,
            extra_cost_bps=extra_cost_bps,
            max_delay_minutes=max_delay_minutes,
            trigger_negative_months=trigger,
            cooldown_months=cooldown,
        )
        design_agg = design_result["aggregate"]
        full_agg = full_result["aggregate"]
        holdout_agg = holdout_result["aggregate"]
        rows.append(
            {
                "trigger_negative_months": int(trigger),
                "cooldown_months": int(cooldown),
                "design_positive_delay_rate": float(design_agg["positive_delay_rate"]),
                "design_worst_delay_total_net_pnl_bps": float(design_agg["worst_delay_total_net_pnl_bps"]),
                "design_total_net_pnl_bps": float(design_agg["total_net_pnl_bps"]),
                "full_positive_delay_rate": float(full_agg["positive_delay_rate"]),
                "full_worst_delay_total_net_pnl_bps": float(full_agg["worst_delay_total_net_pnl_bps"]),
                "full_total_net_pnl_bps": float(full_agg["total_net_pnl_bps"]),
                "holdout_positive_delay_rate": float(holdout_agg["positive_delay_rate"]),
                "holdout_worst_delay_total_net_pnl_bps": float(holdout_agg["worst_delay_total_net_pnl_bps"]),
                "holdout_total_net_pnl_bps": float(holdout_agg["total_net_pnl_bps"]),
            }
        )
        results[(int(trigger), int(cooldown))] = full_result
    return pd.DataFrame(rows), results


def _write_report(payload: dict[str, object], scan: pd.DataFrame, selected_delay_rows: pd.DataFrame) -> None:
    decision = payload["decision"]
    selected = payload["selected_policy"]
    selected_agg = payload["selected_result"]["aggregate"]
    lines = [
        "# Research V75 Fixed Flow Design Selected Combined Policy Results",
        "",
        "## Decision",
        "",
        f"- Selected combined policy passed: `{decision['selected_combined_policy_passed']}`",
        f"- Stronger validation promoted: `{decision['stronger_validation_promoted']}`",
        f"- Failed checks: `{';'.join(decision['failed_checks'])}`",
        "",
        "## Selected Policy",
        "",
        f"- Trigger negative months: `{selected['trigger_negative_months']}`",
        f"- Cooldown months: `{selected['cooldown_months']}`",
        "",
        "## Selected Aggregate",
        "",
        f"- Positive delay rate: `{float(selected_agg['positive_delay_rate']):.6f}`",
        f"- Worst delay total: `{float(selected_agg['worst_delay_total_net_pnl_bps']):.6f}` bps",
        f"- Holdout positive delay rate: `{float(selected_agg['holdout_positive_delay_rate']):.6f}`",
        f"- Worst holdout delay total: `{float(selected_agg['worst_holdout_delay_total_net_pnl_bps']):.6f}` bps",
        "",
        "## Policy Scan",
        "",
        scan.to_csv(index=False).strip(),
        "",
        "## Selected Delay Rows",
        "",
        selected_delay_rows.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V75 selects a cooldown policy using only design folds under the V72 execution contract, then validates the selected policy on the full and holdout ledgers. Cooldown 0 is included as the no-cooldown baseline.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    v72 = json.loads(V72_SUMMARY.read_text(encoding="utf-8"))
    trades = _load_trades(V71_SIGNAL_LEDGER)
    max_delay = int(v72["decision"]["contract_max_delay_minutes"])
    extra_cost = float(v72["decision"]["contract_extra_cost_bps"])
    scan, full_results = _scan_policies(trades, max_delay_minutes=max_delay, extra_cost_bps=extra_cost)
    selected = select_delay_monthly_cooldown_policy(scan)
    trigger = int(selected["trigger_negative_months"])
    cooldown = int(selected["cooldown_months"])
    selected_result = full_results[(trigger, cooldown)]
    selected_delay_rows = pd.DataFrame(selected_result["delays"])
    selected_kept_ledger = selected_result["kept_ledger"]

    scan.to_csv(OUT_DIR / "v75_design_policy_scan.csv", index=False)
    selected_delay_rows.to_csv(OUT_DIR / "v75_selected_delay_rows.csv", index=False)
    selected_kept_ledger.to_csv(OUT_DIR / "v75_selected_kept_trade_ledger.csv", index=False)

    agg = selected_result["aggregate"]
    checks = {
        "all_delay_totals_positive": float(agg["positive_delay_rate"]) == 1.0,
        "worst_delay_total_positive": float(agg["worst_delay_total_net_pnl_bps"]) > 0.0,
        "holdout_all_delay_totals_positive": float(agg["holdout_positive_delay_rate"]) == 1.0,
        "worst_holdout_delay_total_positive": float(agg["worst_holdout_delay_total_net_pnl_bps"]) > 0.0,
        "v72_execution_contract_found": bool(v72["decision"]["execution_contract_found"]),
    }
    failed = [name for name, passed in checks.items() if not passed]
    promoted = bool(not failed)
    payload = {
        "version": "v75_btcusdc_fixed_flow_design_selected_combined_policy",
        "source_v71_signal_ledger": str(V71_SIGNAL_LEDGER),
        "source_v72_summary": str(V72_SUMMARY),
        "design_folds": list(DESIGN_FOLDS),
        "holdout_folds": list(HOLDOUT_FOLDS),
        "contract": {
            "gate_mode": str(v72["decision"]["contract_gate_mode"]),
            "max_delay_minutes": max_delay,
            "extra_cost_bps": extra_cost,
        },
        "selected_policy": {
            "trigger_negative_months": trigger,
            "cooldown_months": cooldown,
            "selection_rule": "design_positive_delay_rate, design_worst_delay_total_net_pnl_bps, design_total_net_pnl_bps",
        },
        "selected_result": {"aggregate": agg},
        "decision": {
            "selected_combined_policy_passed": promoted,
            "stronger_validation_promoted": promoted,
            "checks": checks,
            "failed_checks": failed,
        },
        "outputs": {
            "summary_json": str(OUT_DIR / "v75_summary.json"),
            "design_policy_scan": str(OUT_DIR / "v75_design_policy_scan.csv"),
            "selected_delay_rows": str(OUT_DIR / "v75_selected_delay_rows.csv"),
            "selected_kept_trade_ledger": str(OUT_DIR / "v75_selected_kept_trade_ledger.csv"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v75_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, scan, selected_delay_rows)
    print(json.dumps(payload, indent=2, default=str))
