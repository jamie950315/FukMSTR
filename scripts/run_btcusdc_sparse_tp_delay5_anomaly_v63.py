from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_sparse_tp import (
    annotate_sparse_tp_delay_outcomes,
    summarize_sparse_tp_price_path,
)


ROOT = Path(__file__).resolve().parents[1]
INPUT_BARS = ROOT / "runs" / "research_v48_btcusdc_full_1m_direct_ml_input" / "btcusdc_full_1m_bars.csv"
V62_DIR = ROOT / "runs" / "research_v62_btcusdc_sparse_tp_holdout_entry_delay"
OUT_DIR = ROOT / "runs" / "research_v63_btcusdc_sparse_tp_delay5_anomaly_audit"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V63_DELAY5_ANOMALY_AUDIT_RESULTS.md"

DELAYS = (1, 2, 5, 10, 15, 30, 60)


def _load_bars() -> pd.DataFrame:
    bars = pd.read_csv(INPUT_BARS, parse_dates=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        bars[col] = pd.to_numeric(bars[col], errors="coerce")
    return bars


def _load_ledgers() -> dict[int, pd.DataFrame]:
    ledgers: dict[int, pd.DataFrame] = {}
    for delay in DELAYS:
        path = V62_DIR / f"v62_delay{delay}_holdout_tp80_ledger.csv"
        ledgers[int(delay)] = pd.read_csv(path, parse_dates=["signal_timestamp", "timestamp", "exit_timestamp"])
    return ledgers


def _signal_key_columns() -> list[str]:
    return ["fold", "signal_idx", "signal_timestamp", "signal"]


def _write_report(payload: dict[str, object], anomaly_comparison: pd.DataFrame) -> None:
    lines = [
        "# Research V63 Delay-5 Anomaly Audit Results",
        "",
        "## Purpose",
        "",
        "V63 explains the single V62 holdout entry-delay failure without changing the V60 design-selected rule or thresholds.",
        "",
        "Rule under audit: reversal, 1080m lookback, abs_return_bps q0.99, TP80, no stop loss, horizon reserve 1440m.",
        "",
        "## Finding",
        "",
        str(payload["finding"]),
        "",
        "## Delay Comparison",
        "",
        anomaly_comparison.to_markdown(index=False),
        "",
        "## Files",
        "",
        f"- Delay comparison CSV: `{payload['delay_comparison_csv']}`",
        f"- Price path CSV: `{payload['price_path_csv']}`",
        f"- Summary JSON: `{payload['summary_json']}`",
        "",
        "## Caveat",
        "",
        "This audit explains the historical delay-5 failure point. It does not convert the strategy into future unseen validation.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    bars = _load_bars()
    ledgers = _load_ledgers()
    annotated = annotate_sparse_tp_delay_outcomes(ledgers, quote_surcharge_bps=0.5)
    annotated_path = OUT_DIR / "v63_all_delay_outcomes_annotated.csv"
    annotated.to_csv(annotated_path, index=False)

    loss_rows = annotated.loc[
        (pd.to_numeric(annotated["entry_delay_min"], errors="coerce").astype(int) == 5)
        & (annotated["is_loss_after_surcharge"].astype(bool))
    ].copy()
    if loss_rows.empty:
        raise SystemExit("No delay=5 loss rows found in V62 ledgers")

    key_cols = _signal_key_columns()
    anomaly_keys = loss_rows[key_cols].drop_duplicates()
    comparisons: list[pd.DataFrame] = []
    path_rows: list[pd.DataFrame] = []
    for _, key in anomaly_keys.iterrows():
        mask = pd.Series(True, index=annotated.index)
        for col in key_cols:
            mask &= annotated[col].astype(str) == str(key[col])
        comparison = annotated.loc[mask].copy().sort_values("entry_delay_min")

        stats_rows: list[dict[str, object]] = []
        for _, row in comparison.iterrows():
            stats = summarize_sparse_tp_price_path(
                bars,
                entry_idx=int(row["idx"]),
                horizon_minutes=int(row["horizon_minutes"]),
                signal=int(row["signal"]),
                entry_px=float(row["entry_px"]),
                take_profit_bps=float(row["tp_bps"]),
            )
            stats_rows.append(
                {
                    "entry_delay_min": int(row["entry_delay_min"]),
                    "tp_target_px_path": stats["tp_target_px"],
                    "target_hit_in_path": stats["target_hit"],
                    "first_hit_idx": stats["first_hit_idx"],
                    "first_hit_timestamp": stats["first_hit_timestamp"],
                    "first_hit_px": stats["first_hit_px"],
                    "best_touch_idx": stats["best_touch_idx"],
                    "best_touch_timestamp": stats["best_touch_timestamp"],
                    "best_touch_px": stats["best_touch_px"],
                    "target_miss_bps": stats["target_miss_bps"],
                    "horizon_exit_px_path": stats["horizon_exit_px"],
                    "horizon_gross_pnl_bps_path": stats["horizon_gross_pnl_bps"],
                }
            )
        stats_frame = pd.DataFrame(stats_rows)
        comparison = comparison.merge(stats_frame, on="entry_delay_min", how="left")
        comparisons.append(comparison)

        signal_idx = int(key["signal_idx"])
        max_exit_idx = int(pd.to_numeric(comparison["exit_idx"], errors="coerce").max())
        window = bars.iloc[signal_idx : max_exit_idx + 1].copy()
        window.insert(0, "minutes_from_signal", range(len(window)))
        window.insert(0, "signal_idx", signal_idx)
        for _, row in comparison.iterrows():
            delay = int(row["entry_delay_min"])
            window[f"tp_target_px_delay_{delay}"] = float(row["tp_target_px"])
            window[f"entry_idx_delay_{delay}"] = int(row["idx"])
            window[f"exit_idx_delay_{delay}"] = int(row["exit_idx"])
        path_rows.append(window)

    anomaly_comparison = pd.concat(comparisons, ignore_index=True)
    comparison_cols = [
        "fold",
        "signal_idx",
        "signal_timestamp",
        "entry_delay_min",
        "idx",
        "timestamp",
        "signal",
        "entry_px",
        "tp_target_px",
        "exit_timestamp",
        "exit_reason",
        "exit_px",
        "net_pnl_bps",
        "final_net_pnl_bps",
        "target_hit_in_path",
        "first_hit_timestamp",
        "first_hit_px",
        "best_touch_timestamp",
        "best_touch_px",
        "target_miss_bps",
        "hold_sec",
    ]
    anomaly_comparison = anomaly_comparison[comparison_cols]
    comparison_path = OUT_DIR / "v63_delay5_anomaly_delay_comparison.csv"
    anomaly_comparison.to_csv(comparison_path, index=False)

    price_path = pd.concat(path_rows, ignore_index=True)
    price_path_path = OUT_DIR / "v63_delay5_anomaly_price_path.csv"
    price_path.to_csv(price_path_path, index=False)

    delay5 = anomaly_comparison.loc[anomaly_comparison["entry_delay_min"] == 5].iloc[0]
    finding = (
        "The V62 delay=5 failure is one fold-6 short signal at "
        f"{delay5['signal_timestamp']}. Delay=5 entered at {float(delay5['entry_px']):.1f}, "
        f"setting TP80 at {float(delay5['tp_target_px']):.4f}; the best low before horizon was "
        f"{float(delay5['best_touch_px']):.1f}, missing the target by {float(delay5['target_miss_bps']):.4f} bps, "
        f"then exiting at horizon for {float(delay5['final_net_pnl_bps']):.4f} bps after surcharge. "
        "The other tested delays for the same signal reached TP80 because their entry prices produced easier short targets."
    )
    payload: dict[str, object] = {
        "input_bars": str(INPUT_BARS),
        "v62_dir": str(V62_DIR),
        "rows_annotated": int(len(annotated)),
        "delay5_loss_count": int(len(loss_rows)),
        "anomaly_signal_count": int(len(anomaly_keys)),
        "finding": finding,
        "annotated_csv": str(annotated_path),
        "delay_comparison_csv": str(comparison_path),
        "price_path_csv": str(price_path_path),
        "summary_json": str(OUT_DIR / "v63_summary.json"),
    }
    (OUT_DIR / "v63_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload, anomaly_comparison)
    print(json.dumps(payload, indent=2))
