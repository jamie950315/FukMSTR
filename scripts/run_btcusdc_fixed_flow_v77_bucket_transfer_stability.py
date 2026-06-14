from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import summarize_bucket_transfer_stability


ROOT = Path(__file__).resolve().parents[1]
V75_SUMMARY = ROOT / "runs" / "research_v75_btcusdc_fixed_flow_design_selected_combined_policy" / "v75_summary.json"
V75_SELECTED_LEDGER = ROOT / "runs" / "research_v75_btcusdc_fixed_flow_design_selected_combined_policy" / "v75_selected_kept_trade_ledger.csv"
OUT_DIR = ROOT / "runs" / "research_v77_btcusdc_fixed_flow_bucket_transfer_stability"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V77_FIXED_FLOW_BUCKET_TRANSFER_STABILITY_RESULTS.md"

MIN_SIGN_AGREEMENT_RATE = 0.60
MIN_DESIGN_POSITIVE_HOLDOUT_POSITIVE_RATE = 0.60
MIN_SPEARMAN_RANK_CORRELATION = 0.0


def _load_ledger(path: Path) -> pd.DataFrame:
    trades = pd.read_csv(path)
    trades["timestamp"] = pd.to_datetime(trades["timestamp"], utc=True)
    trades["fold"] = pd.to_numeric(trades["fold"], errors="coerce").astype("Int64")
    trades["entry_delay_minutes"] = pd.to_numeric(trades["entry_delay_minutes"], errors="coerce").astype("Int64")
    trades["entry_hour"] = pd.to_numeric(trades["entry_hour"], errors="coerce").astype("Int64")
    trades["signal_hour"] = pd.to_numeric(trades["signal_hour"], errors="coerce").astype("Int64")
    trades["net_pnl_bps"] = pd.to_numeric(trades["net_pnl_bps"], errors="coerce").fillna(0.0)
    trades["utc_month"] = trades["timestamp"].dt.month.astype(int)
    return trades.dropna(subset=["timestamp", "fold", "entry_delay_minutes", "entry_hour", "signal_hour"]).reset_index(drop=True)


def _frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _passes(aggregate: dict[str, object]) -> bool:
    return bool(
        float(aggregate["sign_agreement_rate"]) >= MIN_SIGN_AGREEMENT_RATE
        and float(aggregate["design_positive_holdout_positive_rate"]) >= MIN_DESIGN_POSITIVE_HOLDOUT_POSITIVE_RATE
        and float(aggregate["spearman_rank_correlation"]) >= MIN_SPEARMAN_RANK_CORRELATION
    )


def _write_report(payload: dict[str, object], results: dict[str, dict[str, object]]) -> None:
    decision = payload["decision"]
    summary = _frame(payload["bucket_summary"])
    lines = [
        "# Research V77 Fixed Flow Bucket Transfer Stability Results",
        "",
        "## Decision",
        "",
        f"- Bucket transfer stable: `{decision['bucket_transfer_stable']}`",
        f"- Stronger validation promoted: `{decision['stronger_validation_promoted']}`",
        f"- Failed buckets: `{';'.join(decision['failed_buckets'])}`",
        "",
        "## Scope",
        "",
        "V77 compares design folds against holdout folds on the selected V75 kept ledger under the V72 execution contract. It checks whether bucket-level performance transfers across time. It does not tune thresholds, exclude new buckets, or promote a new policy.",
        "",
        "## Bucket Summary",
        "",
        summary.to_csv(index=False).strip(),
        "",
    ]
    for bucket_name, result in results.items():
        lines.extend(
            [
                f"## {bucket_name}",
                "",
                _frame(result["buckets"]).to_csv(index=False).strip(),
                "",
            ]
        )
    lines.extend(
        [
            "## Interpretation",
            "",
            "A bucket is considered transferable only if sign agreement, design-positive survival, and rank correlation clear the predeclared floors. Failure here means the apparent regime/hour advantage is not stable enough to use as a promoted improvement.",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    v75 = json.loads(V75_SUMMARY.read_text(encoding="utf-8"))
    design_folds = [int(x) for x in v75["design_folds"]]
    holdout_folds = [int(x) for x in v75["holdout_folds"]]
    trades = _load_ledger(V75_SELECTED_LEDGER)

    bucket_columns = ["signal_hour", "entry_hour", "utc_month", "entry_delay_minutes"]
    results: dict[str, dict[str, object]] = {}
    summary_rows: list[dict[str, object]] = []
    for bucket_col in bucket_columns:
        result = summarize_bucket_transfer_stability(
            trades,
            bucket_col=bucket_col,
            design_folds=design_folds,
            holdout_folds=holdout_folds,
        )
        results[bucket_col] = result
        out_path = OUT_DIR / f"v77_{bucket_col}_transfer.csv"
        _frame(result["buckets"]).to_csv(out_path, index=False)
        agg = result["aggregate"]
        passed = _passes(agg)
        summary_rows.append(
            {
                "bucket_col": bucket_col,
                "bucket_count": int(agg["bucket_count"]),
                "sign_agreement_rate": float(agg["sign_agreement_rate"]),
                "design_positive_holdout_positive_rate": float(agg["design_positive_holdout_positive_rate"]),
                "design_negative_holdout_negative_rate": float(agg["design_negative_holdout_negative_rate"]),
                "spearman_rank_correlation": float(agg["spearman_rank_correlation"]),
                "passed": passed,
            }
        )

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUT_DIR / "v77_bucket_summary.csv", index=False)
    failed_buckets = summary.loc[~summary["passed"].astype(bool), "bucket_col"].astype(str).tolist()
    stable = len(failed_buckets) == 0
    payload = {
        "version": "v77_btcusdc_fixed_flow_bucket_transfer_stability",
        "source_v75_summary": str(V75_SUMMARY),
        "source_v75_selected_ledger": str(V75_SELECTED_LEDGER),
        "design_folds": design_folds,
        "holdout_folds": holdout_folds,
        "contract": v75["contract"],
        "selected_policy": v75["selected_policy"],
        "thresholds": {
            "min_sign_agreement_rate": MIN_SIGN_AGREEMENT_RATE,
            "min_design_positive_holdout_positive_rate": MIN_DESIGN_POSITIVE_HOLDOUT_POSITIVE_RATE,
            "min_spearman_rank_correlation": MIN_SPEARMAN_RANK_CORRELATION,
        },
        "bucket_summary": summary_rows,
        "decision": {
            "bucket_transfer_stable": stable,
            "stronger_validation_promoted": False,
            "failed_buckets": failed_buckets,
        },
        "outputs": {
            "summary_json": str(OUT_DIR / "v77_summary.json"),
            "bucket_summary": str(OUT_DIR / "v77_bucket_summary.csv"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v77_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, results)
    print(json.dumps(payload, indent=2, default=str))
