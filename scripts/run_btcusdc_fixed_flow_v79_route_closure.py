from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import summarize_route_closure_decision


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v79_btcusdc_fixed_flow_route_closure"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V79_FIXED_FLOW_ROUTE_CLOSURE_RESULTS.md"

V26_FULL_PUBLIC = ROOT / "runs" / "research_v26_btcusdc_full_public_replay" / "summary_v26.json"
V68 = ROOT / "runs" / "research_v68_btcusdc_fixed_flow_stability" / "v68_summary.json"
V69 = ROOT / "runs" / "research_v69_btcusdc_fixed_flow_hour_gate" / "v69_summary.json"
V70 = ROOT / "runs" / "research_v70_btcusdc_fixed_flow_extended_validation" / "v70_summary.json"
V72 = ROOT / "runs" / "research_v72_btcusdc_fixed_flow_cost_delay_contract" / "v72_summary.json"
V75 = ROOT / "runs" / "research_v75_btcusdc_fixed_flow_design_selected_combined_policy" / "v75_summary.json"
V77 = ROOT / "runs" / "research_v77_btcusdc_fixed_flow_bucket_transfer_stability" / "v77_summary.json"
V78 = ROOT / "runs" / "research_v78_btcusdc_fixed_flow_prequential_bucket_guard" / "v78_summary.json"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _evidence_rows() -> list[dict[str, object]]:
    v26 = _load(V26_FULL_PUBLIC)
    v68 = _load(V68)
    v69 = _load(V69)
    v70 = _load(V70)
    v72 = _load(V72)
    v75 = _load(V75)
    v77 = _load(V77)
    v78 = _load(V78)
    return [
        {
            "gate": "v26_full_public_replay_gate",
            "version": "V26",
            "required": True,
            "passed": bool(v26["aggregate"]["gate"]["passed"]),
            "metric": f"total={float(v26['aggregate']['notional_total_net_pnl_bps']):.4f} bps; win_rate={float(v26['aggregate']['selected_trade_win_rate']):.4f}",
            "failed_checks": ";".join(v26["aggregate"]["gate"]["failed_checks"]),
            "source": str(V26_FULL_PUBLIC),
        },
        {
            "gate": "v68_base_fixed_flow_stability",
            "version": "V68",
            "required": True,
            "passed": bool(v68["decision"]["passed"]),
            "metric": f"total={float(v68['decision']['total_net_pnl_bps']):.4f} bps; positive_fold_rate={float(v68['decision']['positive_fold_rate']):.4f}; worst_fold={float(v68['decision']['worst_fold_net_pnl_bps']):.4f}",
            "failed_checks": ";".join(v68["decision"]["failed_checks"]),
            "source": str(V68),
        },
        {
            "gate": "v69_locked_design_hour_gate",
            "version": "V69",
            "required": False,
            "passed": bool(v69["decision"]["passed"]),
            "metric": f"total={float(v69['decision']['total_net_pnl_bps']):.4f} bps; holdout_total={float(v69['decision']['holdout_total_net_pnl_bps']):.4f}",
            "failed_checks": ";".join(v69["decision"]["failed_checks"]),
            "source": str(V69),
        },
        {
            "gate": "v70_extended_validation_promoted",
            "version": "V70",
            "required": True,
            "passed": bool(v70["decision"]["stronger_validation_promoted"]),
            "metric": f"month_positive_rate={float(v70['decision']['month_positive_rate']):.4f}; prequential_passed={bool(v70['decision']['stricter_checks']['prequential_dynamic_gate_passed'])}",
            "failed_checks": ";".join(v70["decision"]["failed_stricter_checks"]),
            "source": str(V70),
        },
        {
            "gate": "v72_execution_contract_and_stricter_checks",
            "version": "V72",
            "required": True,
            "passed": bool(v72["decision"]["execution_contract_found"]) and bool(v72["decision"]["stronger_validation_promoted"]),
            "metric": f"contract_found={bool(v72['decision']['execution_contract_found'])}; max_delay={v72['decision']['contract_max_delay_minutes']}; extra_cost={v72['decision']['contract_extra_cost_bps']}; month_positive_rate={float(v72['decision']['month_positive_rate']):.4f}",
            "failed_checks": ";".join(v72["decision"]["failed_stricter_checks"]),
            "source": str(V72),
        },
        {
            "gate": "v75_design_selected_combined_policy_holdout",
            "version": "V75",
            "required": True,
            "passed": bool(v75["decision"]["selected_combined_policy_passed"]),
            "metric": f"holdout_positive_delay_rate={float(v75['selected_result']['aggregate']['holdout_positive_delay_rate']):.4f}; worst_holdout_delay={float(v75['selected_result']['aggregate']['worst_holdout_delay_total_net_pnl_bps']):.4f}",
            "failed_checks": ";".join(v75["decision"]["failed_checks"]),
            "source": str(V75),
        },
        {
            "gate": "v77_bucket_transfer_stability",
            "version": "V77",
            "required": True,
            "passed": bool(v77["decision"]["bucket_transfer_stable"]),
            "metric": "failed_buckets=" + ";".join(v77["decision"]["failed_buckets"]),
            "failed_checks": ";".join(v77["decision"]["failed_buckets"]),
            "source": str(V77),
        },
        {
            "gate": "v78_prequential_bucket_guard_holdout",
            "version": "V78",
            "required": True,
            "passed": bool(v78["decision"]["selected_prequential_guard_passed"]),
            "metric": f"holdout_positive_delay_rate={float(v78['selected_result']['holdout_positive_delay_rate']):.4f}; holdout_total={float(v78['selected_result']['holdout_total_net_pnl_bps']):.4f}",
            "failed_checks": ";".join(v78["decision"]["failed_checks"]),
            "source": str(V78),
        },
    ]


def _write_report(payload: dict[str, object], evidence: pd.DataFrame) -> None:
    decision = payload["decision"]
    lines = [
        "# Research V79 Fixed Flow Route Closure Results",
        "",
        "## Decision",
        "",
        f"- Promote fixed-flow route: `{decision['promote_route']}`",
        f"- Fixed-flow route closed: `{decision['route_closed']}`",
        f"- Failed required gates: `{';'.join(decision['failed_required_gates'])}`",
        "",
        "## Evidence",
        "",
        evidence.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V79 is a route-level non-promotion certificate. V69 remains a historical design-only pass, but later execution, holdout, transfer-stability, and prequential guard checks fail. The fixed-flow route should not be promoted as stable or profitable from the current evidence.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    evidence_rows = _evidence_rows()
    decision = summarize_route_closure_decision(evidence_rows)
    evidence = pd.DataFrame(decision["evidence"])
    evidence.to_csv(OUT_DIR / "v79_route_evidence.csv", index=False)
    payload = {
        "version": "v79_btcusdc_fixed_flow_route_closure",
        "route": "btcusdc_fixed_flow",
        "decision": {key: value for key, value in decision.items() if key != "evidence"},
        "outputs": {
            "summary_json": str(OUT_DIR / "v79_summary.json"),
            "route_evidence": str(OUT_DIR / "v79_route_evidence.csv"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v79_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, evidence)
    print(json.dumps(payload, indent=2, default=str))
