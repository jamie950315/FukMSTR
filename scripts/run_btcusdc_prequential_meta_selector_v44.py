from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import audit_prequential_meta_selector


FEATURE_COLUMNS = (
    "lookback_minutes",
    "horizon_minutes",
    "direction",
    "filter_feature",
    "quantile",
    "threshold",
    "generator_trades",
    "generator_total_net_pnl_bps",
    "generator_mean_net_pnl_bps",
    "generator_win_rate",
    "generator_account_return_pct",
    "generator_day_positive_rate",
    "generator_min_day_net_pnl_bps",
    "selector_trades",
    "selector_total_net_pnl_bps",
    "selector_mean_net_pnl_bps",
    "selector_win_rate",
    "selector_account_return_pct",
    "selector_day_positive_rate",
    "selector_min_day_net_pnl_bps",
)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    source = root / "runs" / "research_v43_btcusdc_nested_recency" / "btcusdc_v43_candidate_evaluations.csv"
    if not source.exists():
        raise SystemExit(f"missing V43 candidate evaluations: {source}")

    out_dir = root / "runs" / "research_v44_btcusdc_prequential_meta_selector"
    out_dir.mkdir(parents=True, exist_ok=True)
    evaluations = pd.read_csv(source)

    aggregates: list[dict[str, object]] = []
    for model_type in ("random_forest", "ridge"):
        for warmup_folds in (2, 3, 4, 5, 6):
            result = audit_prequential_meta_selector(
                evaluations,
                feature_columns=FEATURE_COLUMNS,
                warmup_folds=warmup_folds,
                min_selector_trades=20,
                min_selector_day_positive_rate=0.0,
                model_type=model_type,
                target_account_return_pct=50.0,
            )
            label = f"{model_type}_warmup{warmup_folds}"
            pd.DataFrame(result["folds"]).to_csv(out_dir / f"btcusdc_v44_{label}_folds.csv", index=False)
            aggregates.append({"label": label, **result["aggregate"]})

    summary = pd.DataFrame(aggregates).sort_values(
        [
            "prequential_windows_passed",
            "prequential_total_validation_account_return_pct",
            "prequential_min_validation_account_return_pct",
        ],
        ascending=[False, False, False],
    )
    summary.to_csv(out_dir / "btcusdc_v44_summary.csv", index=False)
    payload = {"version": "v44_btcusdc_prequential_meta_selector_audit", "source": str(source), "runs": summary.to_dict(orient="records")}
    (out_dir / "summary_v44.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# V44 BTCUSDC Prequential Meta-Selector Audit",
        "",
        "V44 trains a candidate-level selector on completed folds only, then selects the highest predicted candidate in the next fold.",
        "",
        "## Aggregate",
        "",
        "```json",
        json.dumps(payload, indent=2),
        "```",
        "",
        "## Ranked Runs",
        "",
        summary.to_csv(index=False).strip(),
        "",
    ]
    (out_dir / "REPORT_V44.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "DONE_V44.marker").write_text("ok\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
