from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import summarize_fixed_family_viability


ROOT = Path(__file__).resolve().parents[1]
INPUT_EVALUATIONS = ROOT / "runs" / "research_v36_btcusdc_aggtrade_flow_ytd_rolling" / "btcusdc_v28_candidate_evaluations.csv"
OUT_DIR = ROOT / "runs" / "research_v81_btcusdc_fixed_family_viability"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V81_BTCUSDC_FIXED_FAMILY_VIABILITY_RESULTS.md"

MIN_ACTIVE_FOLDS = 10
MIN_POSITIVE_FOLD_RATE = 0.70
MIN_TOTAL_ACCOUNT_RETURN_PCT = 0.0
MIN_WORST_FOLD_ACCOUNT_RETURN_PCT = -50.0
MIN_MEDIAN_FOLD_ACCOUNT_RETURN_PCT = 0.0


def _write_report(payload: dict[str, object], families: pd.DataFrame, top_families: pd.DataFrame) -> None:
    aggregate = payload["aggregate"]
    best = aggregate["best_family"]
    best_lines = []
    if isinstance(best, dict):
        for key in [
            "lookback_minutes",
            "horizon_minutes",
            "direction",
            "filter_feature",
            "quantile",
            "active_folds",
            "validation_trades",
            "total_validation_account_return_pct",
            "positive_fold_rate",
            "worst_fold_account_return_pct",
            "median_fold_account_return_pct",
            "passed",
            "failed_checks",
        ]:
            best_lines.append(f"- {key}: `{best.get(key)}`")
    else:
        best_lines.append("- No family rows were available.")

    lines = [
        "# Research V81 BTCUSDC Fixed Family Viability Results",
        "",
        "## Decision",
        "",
        f"- Promote fixed family: `{aggregate['promote_fixed_family']}`",
        f"- Passed family count: `{aggregate['passed_family_count']}`",
        f"- Failed checks: `{';'.join(aggregate['failed_checks'])}`",
        "",
        "## Gate",
        "",
        f"- Min active folds: `{MIN_ACTIVE_FOLDS}`",
        f"- Min positive fold rate: `{MIN_POSITIVE_FOLD_RATE}`",
        f"- Min total account return pct: `{MIN_TOTAL_ACCOUNT_RETURN_PCT}`",
        f"- Min worst fold account return pct: `{MIN_WORST_FOLD_ACCOUNT_RETURN_PCT}`",
        f"- Min median fold account return pct: `{MIN_MEDIAN_FOLD_ACCOUNT_RETURN_PCT}`",
        "",
        "## Best Family",
        "",
        *best_lines,
        "",
        "## Top Families",
        "",
        top_families.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V81 checks whether any fixed BTCUSDC aggTrade-flow family remains stable across the 2026 YTD rolling validation folds. It groups candidates by lookback, horizon, direction, filter feature, and quantile, then evaluates only validation-window outcomes. This is an oracle-style viability screen, not a deployment selector. If no family passes here, this feature family does not justify another threshold-tuning loop.",
        "",
        "The result does not promote a strategy route. The best family still misses the required stability floor, so the next research step should be a genuinely different hypothesis or a stronger data source, not another selection rule over the same candidate family.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    if not INPUT_EVALUATIONS.exists():
        raise SystemExit(f"missing input evaluations: {INPUT_EVALUATIONS}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    evaluations = pd.read_csv(INPUT_EVALUATIONS)
    result = summarize_fixed_family_viability(
        evaluations,
        min_active_folds=MIN_ACTIVE_FOLDS,
        min_positive_fold_rate=MIN_POSITIVE_FOLD_RATE,
        min_total_account_return_pct=MIN_TOTAL_ACCOUNT_RETURN_PCT,
        min_worst_fold_account_return_pct=MIN_WORST_FOLD_ACCOUNT_RETURN_PCT,
        min_median_fold_account_return_pct=MIN_MEDIAN_FOLD_ACCOUNT_RETURN_PCT,
    )
    families = pd.DataFrame(result["families"])
    top_families = families.head(20).copy()
    families.to_csv(OUT_DIR / "v81_fixed_family_viability.csv", index=False)
    top_families.to_csv(OUT_DIR / "v81_top_fixed_families.csv", index=False)
    payload = {
        "version": "v81_btcusdc_fixed_family_viability",
        "input_evaluations": str(INPUT_EVALUATIONS),
        "aggregate": result["aggregate"],
        "outputs": {
            "summary_json": str(OUT_DIR / "v81_summary.json"),
            "family_viability": str(OUT_DIR / "v81_fixed_family_viability.csv"),
            "top_families": str(OUT_DIR / "v81_top_fixed_families.csv"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v81_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, families, top_families)
    print(json.dumps(payload, indent=2, default=str))
