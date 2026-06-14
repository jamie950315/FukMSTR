from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import audit_prequential_family_selector


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    source = root / "runs" / "research_v36_btcusdc_aggtrade_flow_ytd_rolling" / "btcusdc_v28_candidate_evaluations.csv"
    if not source.exists():
        raise SystemExit(f"missing V36 candidate evaluations: {source}")
    out_dir = root / "runs" / "research_v39_btcusdc_aggtrade_flow_ytd_family_selector"
    out_dir.mkdir(parents=True, exist_ok=True)

    evaluations = pd.read_csv(source)
    configs = [
        {
            "name": "full_shape",
            "group_columns": ("lookback_minutes", "horizon_minutes", "direction", "filter_feature", "quantile"),
            "ranking_rule": "prior_pass_total",
            "current_selection_score": "calibration_min_day_net_pnl_bps",
        },
        {
            "name": "coarse_shape",
            "group_columns": ("horizon_minutes", "direction", "filter_feature", "quantile"),
            "ranking_rule": "prior_pass_total",
            "current_selection_score": "calibration_min_day_net_pnl_bps",
        },
        {
            "name": "direction_feature",
            "group_columns": ("direction", "filter_feature"),
            "ranking_rule": "prior_pass_total",
            "current_selection_score": "calibration_min_day_net_pnl_bps",
        },
    ]
    summaries: list[dict[str, object]] = []
    for cfg in configs:
        result = audit_prequential_family_selector(
            evaluations,
            group_columns=cfg["group_columns"],
            warmup_folds=2,
            ranking_rule=str(cfg["ranking_rule"]),
            current_selection_score=str(cfg["current_selection_score"]),
            target_account_return_pct=50.0,
            min_calibration_trades=20,
            min_calibration_day_positive_rate=0.0,
        )
        name = str(cfg["name"])
        folds = pd.DataFrame(result["folds"])
        static = pd.DataFrame(result["static_family_summary"])
        folds.to_csv(out_dir / f"btcusdc_v39_{name}_folds.csv", index=False)
        static.to_csv(out_dir / f"btcusdc_v39_{name}_static_family_summary.csv", index=False)
        summaries.append({"config": name, **result["aggregate"]})

    summary_df = pd.DataFrame(summaries)
    summary_df.to_csv(out_dir / "btcusdc_v39_family_selector_summary.csv", index=False)
    aggregate = {
        "version": "v39_btcusdc_aggtrade_flow_ytd_family_selector",
        "configs": summaries,
        "best_config_by_passed_then_total": summary_df.sort_values(
            ["prequential_windows_passed", "prequential_total_validation_account_return_pct"],
            ascending=[False, False],
        ).iloc[0].to_dict(),
    }
    (out_dir / "summary_v39.json").write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
    lines = [
        "# V39 BTCUSDC AggTrade Flow YTD Family Selector Audit",
        "",
        "V39 tests whether candidate families persist across completed folds strongly enough to select future folds without validation leakage.",
        "",
        "## Summary",
        "",
        summary_df.to_csv(index=False).strip(),
        "",
        "## Aggregate",
        "",
        "```json",
        json.dumps(aggregate, indent=2),
        "```",
        "",
    ]
    (out_dir / "REPORT_V39.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "DONE_V39.marker").write_text("ok\n", encoding="utf-8")
    print(json.dumps(aggregate, indent=2))
