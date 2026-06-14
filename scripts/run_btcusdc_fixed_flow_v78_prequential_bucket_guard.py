from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import apply_prequential_bucket_guard, summarize_delay_stress_grid


ROOT = Path(__file__).resolve().parents[1]
V75_SUMMARY = ROOT / "runs" / "research_v75_btcusdc_fixed_flow_design_selected_combined_policy" / "v75_summary.json"
V75_SELECTED_LEDGER = ROOT / "runs" / "research_v75_btcusdc_fixed_flow_design_selected_combined_policy" / "v75_selected_kept_trade_ledger.csv"
OUT_DIR = ROOT / "runs" / "research_v78_btcusdc_fixed_flow_prequential_bucket_guard"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V78_FIXED_FLOW_PREQUENTIAL_BUCKET_GUARD_RESULTS.md"

BUCKET_COLS = ("signal_hour", "entry_hour", "utc_month", "entry_delay_minutes")
MIN_HISTORY_TRADES = (1, 3, 5, 10)
MIN_CUMULATIVE_PNL_BPS = 0.0


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


def _delay_aggregate(trades: pd.DataFrame) -> dict[str, float | int]:
    summary = summarize_delay_stress_grid(
        trades,
        delay_col="entry_delay_minutes",
        fold_col="fold" if "fold" in trades.columns else None,
        min_positive_delay_rate=1.0,
        min_worst_delay_total_net_pnl_bps=0.0,
    )
    agg = summary["aggregate"]
    return {
        "delay_count": int(agg["delay_count"]),
        "positive_delay_count": int(agg["positive_delay_count"]),
        "positive_delay_rate": float(agg["positive_delay_rate"]),
        "total_net_pnl_bps": float(sum(float(row["total_net_pnl_bps"]) for row in summary["delays"])),
        "worst_delay_total_net_pnl_bps": float(agg["worst_delay_total_net_pnl_bps"]),
        "best_delay_total_net_pnl_bps": float(agg["best_delay_total_net_pnl_bps"]),
        "trade_count": int(len(trades)),
    }


def _scan_policies(trades: pd.DataFrame, *, design_folds: list[int], holdout_folds: list[int]) -> tuple[pd.DataFrame, dict[tuple[str, int], pd.DataFrame]]:
    design_set = set(design_folds)
    holdout_set = set(holdout_folds)
    rows: list[dict[str, object]] = []
    guarded_ledgers: dict[tuple[str, int], pd.DataFrame] = {}
    for bucket_col in BUCKET_COLS:
        for min_history in MIN_HISTORY_TRADES:
            guarded = apply_prequential_bucket_guard(
                trades,
                bucket_col=bucket_col,
                group_cols=["entry_delay_minutes"],
                min_history_trades=min_history,
                min_cumulative_pnl_bps=MIN_CUMULATIVE_PNL_BPS,
                cold_start_keep=True,
            )
            kept = guarded.loc[guarded["guard_keep"].astype(bool)].copy()
            design = kept.loc[kept["fold"].astype(int).isin(design_set)].copy()
            holdout = kept.loc[kept["fold"].astype(int).isin(holdout_set)].copy()
            full_agg = _delay_aggregate(kept)
            design_agg = _delay_aggregate(design)
            holdout_agg = _delay_aggregate(holdout)
            rows.append(
                {
                    "bucket_col": bucket_col,
                    "min_history_trades": int(min_history),
                    "design_positive_delay_rate": float(design_agg["positive_delay_rate"]),
                    "design_worst_delay_total_net_pnl_bps": float(design_agg["worst_delay_total_net_pnl_bps"]),
                    "design_total_net_pnl_bps": float(design_agg["total_net_pnl_bps"]),
                    "design_trade_count": int(design_agg["trade_count"]),
                    "full_positive_delay_rate": float(full_agg["positive_delay_rate"]),
                    "full_worst_delay_total_net_pnl_bps": float(full_agg["worst_delay_total_net_pnl_bps"]),
                    "full_total_net_pnl_bps": float(full_agg["total_net_pnl_bps"]),
                    "full_trade_count": int(full_agg["trade_count"]),
                    "holdout_positive_delay_rate": float(holdout_agg["positive_delay_rate"]),
                    "holdout_worst_delay_total_net_pnl_bps": float(holdout_agg["worst_delay_total_net_pnl_bps"]),
                    "holdout_total_net_pnl_bps": float(holdout_agg["total_net_pnl_bps"]),
                    "holdout_trade_count": int(holdout_agg["trade_count"]),
                }
            )
            guarded_ledgers[(bucket_col, int(min_history))] = kept
    return pd.DataFrame(rows), guarded_ledgers


def _select_policy(scan: pd.DataFrame) -> pd.Series:
    return scan.sort_values(
        [
            "design_positive_delay_rate",
            "design_worst_delay_total_net_pnl_bps",
            "design_total_net_pnl_bps",
            "min_history_trades",
            "bucket_col",
        ],
        ascending=[False, False, False, True, True],
    ).iloc[0]


def _write_report(payload: dict[str, object], scan: pd.DataFrame, selected_delays: pd.DataFrame) -> None:
    decision = payload["decision"]
    selected = payload["selected_policy"]
    selected_result = payload["selected_result"]
    lines = [
        "# Research V78 Fixed Flow Prequential Bucket Guard Results",
        "",
        "## Decision",
        "",
        f"- Selected prequential guard passed: `{decision['selected_prequential_guard_passed']}`",
        f"- Stronger validation promoted: `{decision['stronger_validation_promoted']}`",
        f"- Failed checks: `{';'.join(decision['failed_checks'])}`",
        "",
        "## Selected Policy",
        "",
        f"- Bucket column: `{selected['bucket_col']}`",
        f"- Min history trades: `{selected['min_history_trades']}`",
        f"- Min cumulative PnL: `{selected['min_cumulative_pnl_bps']}` bps",
        "",
        "## Selected Result",
        "",
        f"- Design positive delay rate: `{float(selected_result['design_positive_delay_rate']):.6f}`",
        f"- Full positive delay rate: `{float(selected_result['full_positive_delay_rate']):.6f}`",
        f"- Holdout positive delay rate: `{float(selected_result['holdout_positive_delay_rate']):.6f}`",
        f"- Holdout worst delay: `{float(selected_result['holdout_worst_delay_total_net_pnl_bps']):.6f}` bps",
        f"- Holdout total: `{float(selected_result['holdout_total_net_pnl_bps']):.6f}` bps",
        "",
        "## Policy Scan",
        "",
        scan.to_csv(index=False).strip(),
        "",
        "## Selected Delay Rows",
        "",
        selected_delays.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V78 tests a live-feasible prequential bucket guard: each delay scenario learns only from prior kept trades in the same bucket. The selected guard is chosen by design folds only, then checked on full and holdout folds. It does not change the original signal thresholds.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    v75 = json.loads(V75_SUMMARY.read_text(encoding="utf-8"))
    design_folds = [int(x) for x in v75["design_folds"]]
    holdout_folds = [int(x) for x in v75["holdout_folds"]]
    trades = _load_ledger(V75_SELECTED_LEDGER)
    scan, ledgers = _scan_policies(trades, design_folds=design_folds, holdout_folds=holdout_folds)
    selected = _select_policy(scan)
    bucket_col = str(selected["bucket_col"])
    min_history = int(selected["min_history_trades"])
    selected_ledger = ledgers[(bucket_col, min_history)]
    selected_delays = pd.DataFrame(
        summarize_delay_stress_grid(
            selected_ledger,
            delay_col="entry_delay_minutes",
            fold_col="fold",
            min_positive_delay_rate=1.0,
            min_worst_delay_total_net_pnl_bps=0.0,
        )["delays"]
    )

    scan.to_csv(OUT_DIR / "v78_policy_scan.csv", index=False)
    selected_ledger.to_csv(OUT_DIR / "v78_selected_kept_trade_ledger.csv", index=False)
    selected_delays.to_csv(OUT_DIR / "v78_selected_delay_rows.csv", index=False)

    selected_result = selected.to_dict()
    checks = {
        "full_all_delay_totals_positive": float(selected_result["full_positive_delay_rate"]) == 1.0,
        "full_worst_delay_positive": float(selected_result["full_worst_delay_total_net_pnl_bps"]) > 0.0,
        "holdout_all_delay_totals_positive": float(selected_result["holdout_positive_delay_rate"]) == 1.0,
        "holdout_worst_delay_positive": float(selected_result["holdout_worst_delay_total_net_pnl_bps"]) > 0.0,
        "holdout_trade_count_nonzero": int(selected_result["holdout_trade_count"]) > 0,
    }
    failed = [name for name, passed in checks.items() if not passed]
    passed = not failed
    payload = {
        "version": "v78_btcusdc_fixed_flow_prequential_bucket_guard",
        "source_v75_summary": str(V75_SUMMARY),
        "source_v75_selected_ledger": str(V75_SELECTED_LEDGER),
        "design_folds": design_folds,
        "holdout_folds": holdout_folds,
        "contract": v75["contract"],
        "policy_family": {
            "bucket_cols": list(BUCKET_COLS),
            "min_history_trades": list(MIN_HISTORY_TRADES),
            "min_cumulative_pnl_bps": MIN_CUMULATIVE_PNL_BPS,
            "cold_start_keep": True,
            "selection_rule": "design_positive_delay_rate, design_worst_delay_total_net_pnl_bps, design_total_net_pnl_bps",
        },
        "selected_policy": {
            "bucket_col": bucket_col,
            "min_history_trades": min_history,
            "min_cumulative_pnl_bps": MIN_CUMULATIVE_PNL_BPS,
        },
        "selected_result": selected_result,
        "decision": {
            "selected_prequential_guard_passed": passed,
            "stronger_validation_promoted": passed,
            "checks": checks,
            "failed_checks": failed,
        },
        "outputs": {
            "summary_json": str(OUT_DIR / "v78_summary.json"),
            "policy_scan": str(OUT_DIR / "v78_policy_scan.csv"),
            "selected_kept_trade_ledger": str(OUT_DIR / "v78_selected_kept_trade_ledger.csv"),
            "selected_delay_rows": str(OUT_DIR / "v78_selected_delay_rows.csv"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v78_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, scan, selected_delays)
    print(json.dumps(payload, indent=2, default=str))
