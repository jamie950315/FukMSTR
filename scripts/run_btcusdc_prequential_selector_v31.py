from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import audit_prequential_selector_policies


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    source = root / "runs" / "research_v29_btcusdc_ytd_rolling_broad_probe" / "btcusdc_v28_candidate_evaluations.csv"
    if not source.exists():
        raise SystemExit(f"missing broad probe candidate evaluations: {source}")
    out_dir = root / "runs" / "research_v31_btcusdc_prequential_selector"
    out_dir.mkdir(parents=True, exist_ok=True)

    evaluations = pd.read_csv(source)
    result = audit_prequential_selector_policies(
        evaluations,
        warmup_folds=2,
        ranking_rule="prior_pass_total",
        target_account_return_pct=50.0,
    )
    folds = pd.DataFrame(result["folds"])
    policies = pd.DataFrame(result["policy_results"])
    static = pd.DataFrame(result["static_policy_summary"])
    folds.to_csv(out_dir / "btcusdc_v31_prequential_folds.csv", index=False)
    policies.to_csv(out_dir / "btcusdc_v31_policy_results.csv", index=False)
    static.to_csv(out_dir / "btcusdc_v31_static_policy_summary.csv", index=False)
    (out_dir / "summary_v31.json").write_text(json.dumps({"aggregate": result["aggregate"]}, indent=2), encoding="utf-8")

    top_static = static.head(20) if not static.empty else static
    lines = [
        "# V31 BTCUSDC Prequential Selector Policy Audit",
        "",
        "V31 audits whether simple selector policies can improve BTCUSDC YTD rolling validation without selecting from the current validation fold.",
        "",
        "## Aggregate",
        "",
        "```json",
        json.dumps(result["aggregate"], indent=2),
        "```",
        "",
        "## Prequential Folds",
        "",
        folds.to_csv(index=False).strip(),
        "",
        "## Top Static Policies",
        "",
        top_static.to_csv(index=False).strip(),
        "",
    ]
    (out_dir / "REPORT_V31.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "DONE_V31.marker").write_text("ok\n", encoding="utf-8")
    print(json.dumps(result["aggregate"], indent=2))
