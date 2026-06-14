from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import audit_quantile_band_selector


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "runs" / "research_v42_btcusdc_quantile_band_selector"
    out_dir.mkdir(parents=True, exist_ok=True)
    sources = {
        "aggtrade_flow_ytd": root / "runs" / "research_v36_btcusdc_aggtrade_flow_ytd_rolling" / "btcusdc_v28_candidate_evaluations.csv",
        "kline_ytd_broad": root / "runs" / "research_v29_btcusdc_ytd_rolling_broad_probe" / "btcusdc_v28_candidate_evaluations.csv",
    }
    aggregates: list[dict[str, object]] = []
    for label, source in sources.items():
        if not source.exists():
            raise SystemExit(f"missing candidate evaluations for {label}: {source}")
        evaluations = pd.read_csv(source)
        result = audit_quantile_band_selector(
            evaluations,
            band_columns=("calibration_account_return_pct", "calibration_min_day_net_pnl_bps", "calibration_trades"),
            score_columns=(
                "calibration_account_return_pct",
                "calibration_min_day_net_pnl_bps",
                "calibration_win_rate",
                "calibration_day_positive_rate",
            ),
            bands=((0.0, 0.2), (0.1, 0.3), (0.2, 0.4), (0.3, 0.5), (0.4, 0.6), (0.5, 0.7), (0.6, 0.8), (0.7, 0.9), (0.8, 1.0), (0.9, 1.0), (0.2, 0.8)),
            min_calibration_trades=20,
            min_calibration_day_positive_rate=0.0,
            target_account_return_pct=50.0,
        )
        folds = pd.DataFrame(result["folds"])
        summary = pd.DataFrame(result["summary"])
        folds.to_csv(out_dir / f"btcusdc_v42_{label}_folds.csv", index=False)
        summary.to_csv(out_dir / f"btcusdc_v42_{label}_summary.csv", index=False)
        aggregates.append({"source": label, **result["aggregate"]})

    aggregate = {"version": "v42_btcusdc_quantile_band_selector_audit", "sources": aggregates}
    (out_dir / "summary_v42.json").write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
    lines = [
        "# V42 BTCUSDC Quantile Band Selector Audit",
        "",
        "V42 tests whether avoiding the very top calibration candidates improves BTCUSDC validation stability.",
        "",
        "## Aggregate",
        "",
        "```json",
        json.dumps(aggregate, indent=2),
        "```",
        "",
    ]
    for item in aggregates:
        label = str(item["source"])
        summary = pd.read_csv(out_dir / f"btcusdc_v42_{label}_summary.csv")
        lines += [f"## {label}", "", summary.head(20).to_csv(index=False).strip(), ""]
    (out_dir / "REPORT_V42.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "DONE_V42.marker").write_text("ok\n", encoding="utf-8")
    print(json.dumps(aggregate, indent=2))
