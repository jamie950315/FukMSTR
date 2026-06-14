from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import audit_fixed_family_transfer


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    source = root / "runs" / "research_v45_btcusdc_enhanced_nested_recency" / "btcusdc_v43_candidate_evaluations.csv"
    if not source.exists():
        raise SystemExit(f"missing enhanced candidate evaluations: {source}")

    out_dir = root / "runs" / "research_v46_btcusdc_fixed_family_transfer"
    out_dir.mkdir(parents=True, exist_ok=True)
    evaluations = pd.read_csv(source)
    group_sets = {
        "horizon_direction_feature_quantile": ("horizon_minutes", "direction", "filter_feature", "quantile"),
        "lookback_horizon_direction_feature_quantile": ("lookback_minutes", "horizon_minutes", "direction", "filter_feature", "quantile"),
        "horizon_direction_feature": ("horizon_minutes", "direction", "filter_feature"),
        "direction_feature_quantile": ("direction", "filter_feature", "quantile"),
    }
    score_columns = (
        "selector_account_return_pct",
        "selector_mean_net_pnl_bps",
        "selector_day_positive_rate",
        "selector_min_day_net_pnl_bps",
        "selector_profit_factor",
    )
    aggregates: list[dict[str, object]] = []
    for group_label, group_columns in group_sets.items():
        for score in score_columns:
            result = audit_fixed_family_transfer(
                evaluations,
                group_columns=group_columns,
                train_folds=range(1, 8),
                validation_folds=range(8, 15),
                current_selection_score=score,
                target_account_return_pct=50.0,
                min_current_trades=20,
                current_trades_column="selector_trades",
            )
            label = f"{group_label}_{score}"
            pd.DataFrame(result["train_family_summary"]).to_csv(out_dir / f"btcusdc_v46_{label}_train_summary.csv", index=False)
            pd.DataFrame(result["validation_folds"]).to_csv(out_dir / f"btcusdc_v46_{label}_validation_folds.csv", index=False)
            aggregates.append({"label": label, **result["aggregate"]})

    summary = pd.DataFrame(aggregates).sort_values(
        ["validation_windows_passed", "validation_total_account_return_pct", "validation_min_account_return_pct"],
        ascending=[False, False, False],
    )
    summary.to_csv(out_dir / "btcusdc_v46_summary.csv", index=False)
    payload = {"version": "v46_btcusdc_fixed_family_transfer_audit", "source": str(source), "runs": summary.to_dict(orient="records")}
    (out_dir / "summary_v46.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [
        "# V46 BTCUSDC Fixed Family Transfer Audit",
        "",
        "V46 selects a fixed candidate family using folds 1-7 only, then evaluates that family on folds 8-14.",
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
    (out_dir / "REPORT_V46.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "DONE_V46.marker").write_text("ok\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
