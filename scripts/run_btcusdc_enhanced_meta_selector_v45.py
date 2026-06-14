from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import audit_prequential_meta_selector, run_btcusdc_nested_recency_validation


BASE_FEATURE_COLUMNS = (
    "lookback_minutes",
    "horizon_minutes",
    "direction",
    "filter_feature",
    "quantile",
    "threshold",
)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    bars_path = root / "runs" / "research_v36_btcusdc_aggtrade_flow_ytd_rolling_input" / "btcusdc_aggtrade_1m_flow_bars.csv"
    if not bars_path.exists():
        raise SystemExit(f"missing BTCUSDC aggTrade flow bars: {bars_path}")

    nested_dir = root / "runs" / "research_v45_btcusdc_enhanced_nested_recency"
    nested = run_btcusdc_nested_recency_validation(
        kline_paths=[bars_path],
        out_dir=nested_dir,
        start_date="2026-01-01",
        end_date="2026-06-10",
        calibration_days=20,
        selector_days=10,
        validation_days=10,
        step_days=10,
        lookbacks=(5, 10, 15, 30, 60, 120, 240),
        horizons=(60, 120, 240),
        directions=("flow_momentum", "flow_reversal", "momentum", "reversal"),
        filter_features=("abs_flow_imbalance", "volume_ratio", "range_bps"),
        quantiles=(0.6, 0.7, 0.8, 0.85, 0.9, 0.94, 0.98),
        min_selector_trades=20,
        min_selector_day_positive_rate=0.5,
        leverage=8.0,
        fee_bps=8.5,
        target_account_return_pct=50.0,
        clean=True,
    )

    evaluations = pd.read_csv(nested_dir / "btcusdc_v43_candidate_evaluations.csv")
    metric_features = tuple(c for c in evaluations.columns if c.startswith("generator_") or c.startswith("selector_"))
    feature_columns = BASE_FEATURE_COLUMNS + metric_features
    out_dir = root / "runs" / "research_v45_btcusdc_enhanced_meta_selector"
    out_dir.mkdir(parents=True, exist_ok=True)

    aggregates: list[dict[str, object]] = []
    for model_type in ("random_forest", "ridge"):
        for warmup_folds in (2, 3, 4, 5, 6):
            result = audit_prequential_meta_selector(
                evaluations,
                feature_columns=feature_columns,
                warmup_folds=warmup_folds,
                min_selector_trades=20,
                min_selector_day_positive_rate=0.0,
                model_type=model_type,
                target_account_return_pct=50.0,
            )
            label = f"{model_type}_warmup{warmup_folds}"
            pd.DataFrame(result["folds"]).to_csv(out_dir / f"btcusdc_v45_{label}_folds.csv", index=False)
            aggregates.append({"label": label, **result["aggregate"]})

    summary = pd.DataFrame(aggregates).sort_values(
        [
            "prequential_windows_passed",
            "prequential_total_validation_account_return_pct",
            "prequential_min_validation_account_return_pct",
        ],
        ascending=[False, False, False],
    )
    summary.to_csv(out_dir / "btcusdc_v45_summary.csv", index=False)
    payload = {
        "version": "v45_btcusdc_enhanced_meta_selector_audit",
        "nested_aggregate": nested["aggregate"],
        "nested_candidate_evaluations": str(nested_dir / "btcusdc_v43_candidate_evaluations.csv"),
        "runs": summary.to_dict(orient="records"),
    }
    (out_dir / "summary_v45.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [
        "# V45 BTCUSDC Enhanced Meta-Selector Audit",
        "",
        "V45 reruns nested recency after adding path-shape metrics, then tests prequential candidate-level meta-selection with the enhanced feature set.",
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
    (out_dir / "REPORT_V45.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "DONE_V45.marker").write_text("ok\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
