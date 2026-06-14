from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import summarize_cost_edge_viability


ROOT = Path(__file__).resolve().parents[1]
INPUT_LEDGER = ROOT / "runs" / "research_v26_btcusdc_full_public_replay" / "btcusdc_contract_trade_ledger.csv"
OUT_DIR = ROOT / "runs" / "research_v83_btcusdc_cost_edge_audit"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V83_BTCUSDC_COST_EDGE_AUDIT_RESULTS.md"

COST_BPS_VALUES = (0.0, 0.05, 0.1, 0.125, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 8.5)
MIN_TOTAL_NET_PNL_BPS = 0.0
MIN_POSITIVE_FOLD_RATE = 1.0
MIN_POSITIVE_MONTH_RATE = 1.0
MIN_WIN_RATE = 0.50


def _write_report(payload: dict[str, object], scenarios: pd.DataFrame) -> None:
    aggregate = payload["aggregate"]
    lines = [
        "# Research V83 BTCUSDC Cost Edge Audit Results",
        "",
        "## Decision",
        "",
        f"- Has passing cost scenario: `{aggregate['has_passing_cost']}`",
        f"- Best passing variant: `{aggregate['best_passing_variant']}`",
        f"- Best passing cost: `{aggregate['best_passing_cost_bps']}`",
        f"- Original best passing cost: `{aggregate['original_best_passing_cost_bps']}`",
        f"- Inverted best passing cost: `{aggregate['inverted_best_passing_cost_bps']}`",
        "",
        "## Gate",
        "",
        f"- Min total net PnL: `{MIN_TOTAL_NET_PNL_BPS}` bps",
        f"- Min positive fold rate: `{MIN_POSITIVE_FOLD_RATE}`",
        f"- Min positive month rate: `{MIN_POSITIVE_MONTH_RATE}`",
        f"- Min win rate: `{MIN_WIN_RATE}`",
        "",
        "## Cost Scenarios",
        "",
        scenarios.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V83 separates gross signal edge from execution cost on the V26 BTCUSDC full public replay ledger. Original direction is negative even at zero added cost. Inverted direction is mildly positive at zero and very low cost, but it still fails fold and month stability, and it collapses before realistic taker cost.",
        "",
        "The result does not promote a strategy route. The loss is cost-amplified, but there is no stable gross edge strong enough to justify deployment or another threshold-tuning loop.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    if not INPUT_LEDGER.exists():
        raise SystemExit(f"missing input ledger: {INPUT_LEDGER}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    trades = pd.read_csv(INPUT_LEDGER)
    result = summarize_cost_edge_viability(
        trades,
        cost_bps_values=COST_BPS_VALUES,
        variants=("original", "inverted"),
        min_total_net_pnl_bps=MIN_TOTAL_NET_PNL_BPS,
        min_positive_fold_rate=MIN_POSITIVE_FOLD_RATE,
        min_positive_month_rate=MIN_POSITIVE_MONTH_RATE,
        min_win_rate=MIN_WIN_RATE,
    )
    scenarios = pd.DataFrame(result["scenarios"])
    scenarios.to_csv(OUT_DIR / "v83_cost_edge_scenarios.csv", index=False)
    payload = {
        "version": "v83_btcusdc_cost_edge_audit",
        "input_ledger": str(INPUT_LEDGER),
        "aggregate": result["aggregate"],
        "outputs": {
            "summary_json": str(OUT_DIR / "v83_summary.json"),
            "cost_edge_scenarios": str(OUT_DIR / "v83_cost_edge_scenarios.csv"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v83_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, scenarios)
    print(json.dumps(payload, indent=2, default=str))
