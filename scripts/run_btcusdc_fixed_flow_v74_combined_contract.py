from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import summarize_delay_monthly_cooldown_grid


ROOT = Path(__file__).resolve().parents[1]
V71_SIGNAL_LEDGER = ROOT / "runs" / "research_v71_btcusdc_fixed_flow_dense_delay_stress" / "v71_dense_delay_signal_hour_gated_ledgers.csv"
V72_SUMMARY = ROOT / "runs" / "research_v72_btcusdc_fixed_flow_cost_delay_contract" / "v72_summary.json"
V73_SUMMARY = ROOT / "runs" / "research_v73_btcusdc_fixed_flow_monthly_cooldown" / "v73_summary.json"
OUT_DIR = ROOT / "runs" / "research_v74_btcusdc_fixed_flow_combined_contract"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V74_FIXED_FLOW_COMBINED_CONTRACT_RESULTS.md"

HOLDOUT_FOLDS = (5, 6, 7)


def _load_trades(path: Path) -> pd.DataFrame:
    trades = pd.read_csv(path)
    trades["timestamp"] = pd.to_datetime(trades["timestamp"], utc=True)
    trades["net_pnl_bps"] = pd.to_numeric(trades["net_pnl_bps"], errors="coerce").fillna(0.0)
    trades["entry_delay_minutes"] = pd.to_numeric(trades["entry_delay_minutes"], errors="coerce").astype("Int64")
    trades["fold"] = pd.to_numeric(trades["fold"], errors="coerce").astype("Int64")
    return trades.dropna(subset=["entry_delay_minutes", "fold"]).sort_values("timestamp").reset_index(drop=True)


def _write_report(payload: dict[str, object], delay_rows: pd.DataFrame) -> None:
    decision = payload["decision"]
    contract = payload["contract"]
    aggregate = payload["combined_contract"]["aggregate"]
    lines = [
        "# Research V74 Fixed Flow Combined Contract Results",
        "",
        "## Decision",
        "",
        f"- Combined contract passed: `{decision['combined_contract_passed']}`",
        f"- Stronger validation promoted: `{decision['stronger_validation_promoted']}`",
        f"- Failed checks: `{';'.join(decision['failed_checks'])}`",
        "",
        "## Contract",
        "",
        f"- Gate mode: `{contract['gate_mode']}`",
        f"- Max entry delay: `{contract['max_delay_minutes']}` minutes",
        f"- Extra cost: `{contract['extra_cost_bps']}` bps per trade",
        f"- Monthly cooldown: trigger `{contract['trigger_negative_months']}` negative month, skip `{contract['cooldown_months']}` months",
        "",
        "## Aggregate",
        "",
        f"- Delay count: `{aggregate['delay_count']}`",
        f"- Positive delay rate: `{float(aggregate['positive_delay_rate']):.6f}`",
        f"- Worst delay total: `{float(aggregate['worst_delay_total_net_pnl_bps']):.6f}` bps",
        f"- Holdout positive delay rate: `{float(aggregate['holdout_positive_delay_rate']):.6f}`",
        f"- Worst holdout delay total: `{float(aggregate['worst_holdout_delay_total_net_pnl_bps']):.6f}` bps",
        "",
        "## Delay Rows",
        "",
        delay_rows.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V74 combines the V72 execution contract with the V73 monthly cooldown policy. The rules are fixed before this audit: signal-hour gate, max 60-minute entry delay, 16 bps extra cost, and a one-loss-month two-month cooldown.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    v72 = json.loads(V72_SUMMARY.read_text(encoding="utf-8"))
    v73 = json.loads(V73_SUMMARY.read_text(encoding="utf-8"))
    contract = {
        "gate_mode": str(v72["decision"]["contract_gate_mode"]),
        "max_delay_minutes": int(v72["decision"]["contract_max_delay_minutes"]),
        "extra_cost_bps": float(v72["decision"]["contract_extra_cost_bps"]),
        "trigger_negative_months": int(v73["selected_policy"]["trigger_negative_months"]),
        "cooldown_months": int(v73["selected_policy"]["cooldown_months"]),
    }
    trades = _load_trades(V71_SIGNAL_LEDGER)
    combined = summarize_delay_monthly_cooldown_grid(
        trades,
        extra_cost_bps=float(contract["extra_cost_bps"]),
        max_delay_minutes=int(contract["max_delay_minutes"]),
        trigger_negative_months=int(contract["trigger_negative_months"]),
        cooldown_months=int(contract["cooldown_months"]),
        holdout_folds=HOLDOUT_FOLDS,
    )
    delay_rows = pd.DataFrame(combined["delays"])
    kept_ledger = combined["kept_ledger"]
    delay_rows.to_csv(OUT_DIR / "v74_delay_rows.csv", index=False)
    kept_ledger.to_csv(OUT_DIR / "v74_kept_trade_ledger.csv", index=False)
    aggregate = combined["aggregate"]
    checks = {
        "all_delay_totals_positive": float(aggregate["positive_delay_rate"]) == 1.0,
        "worst_delay_total_positive": float(aggregate["worst_delay_total_net_pnl_bps"]) > 0.0,
        "holdout_all_delay_totals_positive": float(aggregate["holdout_positive_delay_rate"]) == 1.0,
        "worst_holdout_delay_total_positive": float(aggregate["worst_holdout_delay_total_net_pnl_bps"]) > 0.0,
        "v72_execution_contract_found": bool(v72["decision"]["execution_contract_found"]),
        "v73_monthly_cooldown_promoted": bool(v73["decision"]["monthly_cooldown_promoted"]),
    }
    failed = [name for name, passed in checks.items() if not passed]
    promoted = bool(not failed)
    payload = {
        "version": "v74_btcusdc_fixed_flow_combined_contract",
        "source_v71_signal_ledger": str(V71_SIGNAL_LEDGER),
        "source_v72_summary": str(V72_SUMMARY),
        "source_v73_summary": str(V73_SUMMARY),
        "contract": contract,
        "combined_contract": {"aggregate": aggregate},
        "decision": {
            "combined_contract_passed": promoted,
            "stronger_validation_promoted": promoted,
            "checks": checks,
            "failed_checks": failed,
        },
        "outputs": {
            "summary_json": str(OUT_DIR / "v74_summary.json"),
            "delay_rows": str(OUT_DIR / "v74_delay_rows.csv"),
            "kept_trade_ledger": str(OUT_DIR / "v74_kept_trade_ledger.csv"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v74_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, delay_rows)
    print(json.dumps(payload, indent=2, default=str))
