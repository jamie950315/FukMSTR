from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import summarize_rescue_hypothesis_closure


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v85_btcusdc_rescue_hypothesis_closure"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V85_BTCUSDC_RESCUE_HYPOTHESIS_CLOSURE_RESULTS.md"

V80 = ROOT / "runs" / "research_v80_btcusdc_route_inventory" / "v80_summary.json"
V81 = ROOT / "runs" / "research_v81_btcusdc_fixed_family_viability" / "v81_summary.json"
V82 = ROOT / "runs" / "research_v82_btcusdc_signal_inversion_audit" / "v82_summary.json"
V83 = ROOT / "runs" / "research_v83_btcusdc_cost_edge_audit" / "v83_summary.json"
V84 = ROOT / "runs" / "research_v84_btcusdc_exit_lane_bucket_audit" / "v84_summary.json"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _evidence_rows() -> list[dict[str, object]]:
    v80 = _load(V80)
    v81 = _load(V81)
    v82 = _load(V82)
    v83 = _load(V83)
    v84 = _load(V84)
    return [
        {
            "hypothesis": "existing_route_inventory",
            "version": "V80",
            "required": True,
            "closed": not v80["decision"]["promoted_routes"] and not v80["decision"]["needs_validation_routes"],
            "metric": f"closed_routes={len(v80['decision']['closed_routes'])}; next_action={v80['decision']['next_action']}",
            "reason": "no existing promoted or needs-validation BTCUSDC route",
            "source": str(V80),
        },
        {
            "hypothesis": "fixed_family_rescue",
            "version": "V81",
            "required": True,
            "closed": not bool(v81["aggregate"]["promote_fixed_family"]),
            "metric": f"families={v81['aggregate']['family_count']}; passed={v81['aggregate']['passed_family_count']}; best_positive_fold_rate={float(v81['aggregate']['best_positive_fold_rate']):.6f}",
            "reason": "no stable fixed family across YTD rolling validation",
            "source": str(V81),
        },
        {
            "hypothesis": "signal_inversion_rescue",
            "version": "V82",
            "required": True,
            "closed": not bool(v82["aggregate"]["promote_inverted_signal"]),
            "metric": f"inverted_total={float(v82['inverted']['total_net_pnl_bps']):.4f}; inverted_fold_rate={float(v82['inverted']['positive_fold_rate']):.4f}; inverted_month_rate={float(v82['inverted']['positive_month_rate']):.4f}",
            "reason": "flipping direction remains deeply negative and unstable",
            "source": str(V82),
        },
        {
            "hypothesis": "cost_edge_rescue",
            "version": "V83",
            "required": True,
            "closed": not bool(v83["aggregate"]["has_passing_cost"]),
            "metric": f"scenarios={v83['aggregate']['scenario_count']}; passed={v83['aggregate']['passed_scenario_count']}; best_cost={v83['aggregate']['best_passing_cost_bps']}",
            "reason": "no original or inverted cost scenario passes gross-edge stability gate",
            "source": str(V83),
        },
        {
            "hypothesis": "pretrade_bucket_rescue",
            "version": "V84",
            "required": True,
            "closed": not bool(v84["aggregate"]["promote_pretrade_bucket"]),
            "metric": f"passed_pretrade={v84['aggregate']['passed_pretrade_bucket_count']}; passed_outcome={v84['aggregate']['passed_outcome_bucket_count']}",
            "reason": "only outcome-only take-profit bucket passes; no pretrade subset passes",
            "source": str(V84),
        },
    ]


def _write_report(payload: dict[str, object], evidence: pd.DataFrame) -> None:
    lines = [
        "# Research V85 BTCUSDC Rescue Hypothesis Closure Results",
        "",
        "## Decision",
        "",
        f"- All required rescue hypotheses closed: `{payload['all_required_rescue_hypotheses_closed']}`",
        f"- Open required hypotheses: `{';'.join(payload['open_required_hypotheses'])}`",
        f"- Next action: `{payload['next_action']}`",
        "",
        "## Evidence",
        "",
        evidence.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V85 consolidates V80 through V84. Existing BTCUSDC routes are closed, fixed-family rescue fails, signal inversion fails, cost-edge rescue fails, and pretrade bucket rescue fails. The only passing subset is an outcome-only take-profit bucket, which cannot be used before entry.",
        "",
        "This does not mean the overall research goal is complete. It means this rescue path is exhausted. The aligned next step is a genuinely new hypothesis or stronger data source, not another threshold or lane adjustment on the same BTCUSDC route family.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    evidence_rows = _evidence_rows()
    closure = summarize_rescue_hypothesis_closure(evidence_rows)
    evidence = pd.DataFrame(closure["evidence"])
    evidence.to_csv(OUT_DIR / "v85_rescue_evidence.csv", index=False)
    payload = {
        "version": "v85_btcusdc_rescue_hypothesis_closure",
        **{key: value for key, value in closure.items() if key != "evidence"},
        "outputs": {
            "summary_json": str(OUT_DIR / "v85_summary.json"),
            "rescue_evidence": str(OUT_DIR / "v85_rescue_evidence.csv"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v85_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, evidence)
    print(json.dumps(payload, indent=2, default=str))
