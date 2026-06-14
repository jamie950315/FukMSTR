from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import summarize_route_inventory_decision


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v80_btcusdc_route_inventory"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V80_BTCUSDC_ROUTE_INVENTORY_RESULTS.md"

V26_FULL_PUBLIC = ROOT / "runs" / "research_v26_btcusdc_full_public_replay" / "summary_v26.json"
V48_DIRECT_ML = ROOT / "runs" / "research_v48_btcusdc_full_1m_direct_ml_probe" / "summary_v48.json"
V52_FORMAL_FAMILY = ROOT / "runs" / "research_v52_btcusdc_formal_family_probe" / "formal_family_probe_summary.json"
V67_SPARSE_TP = ROOT / "runs" / "research_v67_btcusdc_sparse_tp_route_closure" / "v67_summary.json"
V79_FIXED_FLOW = ROOT / "runs" / "research_v79_btcusdc_fixed_flow_route_closure" / "v79_summary.json"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _routes() -> list[dict[str, object]]:
    v26 = _load(V26_FULL_PUBLIC)
    v48 = _load(V48_DIRECT_ML)
    v52 = _load(V52_FORMAL_FAMILY)
    v67 = _load(V67_SPARSE_TP)
    v79 = _load(V79_FIXED_FLOW)
    best_family = v52["best_total_policy"]
    selected_selectors = [row for row in v52["selectors"] if bool(row.get("selected", False))]
    selected_holdout_passed = any(float(row.get("holdout_passed", 0.0)) >= float(row.get("holdout_active", 1.0)) for row in selected_selectors)
    return [
        {
            "route": "true_public_replay_baseline",
            "family": "baseline",
            "status": "closed",
            "promoted": False,
            "reason": "full_public_gate_failed",
            "metric": f"total={float(v26['aggregate']['notional_total_net_pnl_bps']):.4f} bps; win_rate={float(v26['aggregate']['selected_trade_win_rate']):.4f}",
            "source": str(V26_FULL_PUBLIC),
        },
        {
            "route": "sparse_tp",
            "family": "sparse_take_profit",
            "status": "closed" if str(v67["decision"]["status"]) == "reject" else "needs_validation",
            "promoted": bool(v67["decision"]["promote_sparse_tp"]),
            "reason": ";".join(v67["decision"]["primary_reasons"]),
            "metric": f"v64_pass_rate={float(v67['v64_dense_delay']['pass_rate']):.4f}; selected_holdout_pass_count={int(v67['v66_design_robust_selector']['selected_holdout_pass_count'])}",
            "source": str(V67_SPARSE_TP),
        },
        {
            "route": "fixed_flow",
            "family": "aggtrade_flow",
            "status": "closed" if bool(v79["decision"]["route_closed"]) else "promoted",
            "promoted": bool(v79["decision"]["promote_route"]),
            "reason": "route_closure_failed_required_gates=" + ";".join(v79["decision"]["failed_required_gates"]),
            "metric": f"passed_required={int(v79['decision']['passed_required_gate_count'])}/{int(v79['decision']['required_gate_count'])}",
            "source": str(V79_FIXED_FLOW),
        },
        {
            "route": "direct_ml_1m",
            "family": "direct_ml",
            "status": "closed" if not bool(v48["gate_passed"]) else "promoted",
            "promoted": bool(v48["gate_passed"]),
            "reason": str(v48["conclusion"]),
            "metric": f"best_horizon_total={float(max(row['total'] for row in v48['horizon_summary'])):.4f} bps; gate_passed={bool(v48['gate_passed'])}",
            "source": str(V48_DIRECT_ML),
        },
        {
            "route": "formal_family_selector",
            "family": "family_selector",
            "status": "closed" if not selected_holdout_passed else "needs_validation",
            "promoted": False,
            "reason": "design-selected selectors failed holdout" if not selected_holdout_passed else "selector requires independent validation",
            "metric": f"best_total_policy={best_family['policy_id']}; best_total={float(best_family['total']):.4f}; selected_holdout_passed={selected_holdout_passed}",
            "source": str(V52_FORMAL_FAMILY),
        },
    ]


def _write_report(payload: dict[str, object], routes: pd.DataFrame) -> None:
    decision = payload["decision"]
    lines = [
        "# Research V80 BTCUSDC Route Inventory Results",
        "",
        "## Decision",
        "",
        f"- Promoted routes: `{';'.join(decision['promoted_routes'])}`",
        f"- Needs validation routes: `{';'.join(decision['needs_validation_routes'])}`",
        f"- Closed routes: `{';'.join(decision['closed_routes'])}`",
        f"- Next action: `{decision['next_action']}`",
        "",
        "## Route Inventory",
        "",
        routes.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V80 finds no currently promoted BTCUSDC strategy route in the existing evidence. Sparse TP and fixed-flow are formally closed. Direct ML and formal family selectors do not have a promotion-grade holdout result. The next aligned work is to create or validate a genuinely new hypothesis, preferably with stronger out-of-sample evidence and execution modeling from the start.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    routes = _routes()
    decision = summarize_route_inventory_decision(routes)
    route_frame = pd.DataFrame(decision["routes"])
    route_frame.to_csv(OUT_DIR / "v80_route_inventory.csv", index=False)
    payload = {
        "version": "v80_btcusdc_route_inventory",
        "decision": {key: value for key, value in decision.items() if key != "routes"},
        "outputs": {
            "summary_json": str(OUT_DIR / "v80_summary.json"),
            "route_inventory": str(OUT_DIR / "v80_route_inventory.csv"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v80_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, route_frame)
    print(json.dumps(payload, indent=2, default=str))
