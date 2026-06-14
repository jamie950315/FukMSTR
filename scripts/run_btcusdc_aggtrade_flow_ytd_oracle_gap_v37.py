from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import audit_candidate_selection_gap


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    source = root / "runs" / "research_v36_btcusdc_aggtrade_flow_ytd_rolling" / "btcusdc_v28_candidate_evaluations.csv"
    if not source.exists():
        raise SystemExit(f"missing V36 candidate evaluations: {source}")
    out_dir = root / "runs" / "research_v37_btcusdc_aggtrade_flow_ytd_oracle_gap"
    out_dir.mkdir(parents=True, exist_ok=True)

    evaluations = pd.read_csv(source)
    result = audit_candidate_selection_gap(evaluations, target_account_return_pct=50.0)
    folds = pd.DataFrame(result["folds"])
    folds.to_csv(out_dir / "btcusdc_v37_oracle_gap_folds.csv", index=False)
    (out_dir / "summary_v37.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# V37 BTCUSDC AggTrade Flow YTD Oracle Gap Audit",
        "",
        "V37 compares oracle validation candidates against calibration-selected candidates for the V36 YTD aggTrade flow rolling run.",
        "",
        "## Aggregate",
        "",
        "```json",
        json.dumps(result["aggregate"], indent=2),
        "```",
        "",
        "## Fold Gap",
        "",
        folds.to_csv(index=False).strip(),
        "",
    ]
    (out_dir / "REPORT_V37.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "DONE_V37.marker").write_text("ok\n", encoding="utf-8")
    print(json.dumps(result["aggregate"], indent=2))
