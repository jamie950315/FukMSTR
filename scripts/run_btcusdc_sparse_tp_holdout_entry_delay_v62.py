from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_contract_lock import BTCUSDCContractPolicy, run_btcusdc_contract_lock
from lob_microprice_lab.btcusdc_sparse_tp import (
    SparseTakeProfitPolicy,
    apply_take_profit_exit,
    build_sparse_abs_return_entries,
    sparse_tp_to_contract_source_ledger,
    summarize_sparse_tp_outcomes,
)


ROOT = Path(__file__).resolve().parents[1]
INPUT_BARS = ROOT / "runs" / "research_v48_btcusdc_full_1m_direct_ml_input" / "btcusdc_full_1m_bars.csv"
OUT_DIR = ROOT / "runs" / "research_v62_btcusdc_sparse_tp_holdout_entry_delay"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V62_HOLDOUT_ENTRY_DELAY_RESULTS.md"

FOLDS = (
    (1, "2024-01-05", "2025-04-04", "2025-04-04", "2025-06-03"),
    (2, "2024-03-05", "2025-06-03", "2025-06-03", "2025-08-02"),
    (3, "2024-05-04", "2025-08-02", "2025-08-02", "2025-10-01"),
    (4, "2024-07-03", "2025-10-01", "2025-10-01", "2025-11-30"),
    (5, "2024-09-01", "2025-11-30", "2025-11-30", "2026-01-29"),
    (6, "2024-10-31", "2026-01-29", "2026-01-29", "2026-03-30"),
    (7, "2024-12-30", "2026-03-30", "2026-03-30", "2026-05-29"),
)

HOLDOUT_FOLDS = {5, 6, 7}
DELAYS = (1, 2, 5, 10, 15, 30, 60)
RULE = {
    "name": "v60_design_selected_reversal_1080_q099",
    "label": "V60 design-selected reversal 1080m q0.99",
    "lookback_minutes": 1080,
    "quantile": 0.9900,
    "direction": "reversal",
}


def _load_bars() -> pd.DataFrame:
    bars = pd.read_csv(INPUT_BARS, parse_dates=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    for col in ["open", "high", "low", "close", "volume"]:
        bars[col] = pd.to_numeric(bars[col], errors="coerce")
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars["replay_date"] = bars["timestamp"].dt.date.astype(str)
    return bars


def _run_delay(bars: pd.DataFrame, delay: int) -> dict[str, object]:
    entries = build_sparse_abs_return_entries(
        bars,
        folds=FOLDS,
        entry_delay_minutes=int(delay),
        lookback_minutes=int(RULE["lookback_minutes"]),
        horizon_minutes=1440,
        quantile=float(RULE["quantile"]),
        direction=str(RULE["direction"]),
    )
    entries = entries.loc[pd.to_numeric(entries["fold"], errors="coerce").astype(int).isin(HOLDOUT_FOLDS)].reset_index(drop=True)
    entries_path = OUT_DIR / f"v62_delay{delay}_holdout_entries.csv"
    entries.to_csv(entries_path, index=False)

    tp_ledger = apply_take_profit_exit(entries, bars, SparseTakeProfitPolicy(take_profit_bps=80.0, horizon_minutes=1440))
    tp_path = OUT_DIR / f"v62_delay{delay}_holdout_tp80_ledger.csv"
    tp_ledger.to_csv(tp_path, index=False)

    source = sparse_tp_to_contract_source_ledger(tp_ledger)
    source_path = OUT_DIR / f"v62_delay{delay}_holdout_source_ledger_for_contract_gate.csv"
    source.to_csv(source_path, index=False)

    gate_dir = ROOT / f"runs/research_v62_delay{delay}_holdout_contract_gate"
    gate = run_btcusdc_contract_lock(
        v24_run_dir=ROOT / "runs" / "research_v24_btc_adaptive_exit_safety_lock",
        out_dir=gate_dir,
        policy=BTCUSDCContractPolicy(source_symbol=f"BTCUSDC V62 holdout-only {RULE['label']} entry delay {delay}m ledger"),
        btcusdc_ledger=source_path,
        data_start="2024-01-04",
        data_end="2026-06-10",
        clean=True,
    )
    agg = gate["aggregate"]
    summary = summarize_sparse_tp_outcomes(tp_ledger, quote_surcharge_bps=0.5)
    return {
        "entry_delay_min": int(delay),
        "entries_path": str(entries_path),
        "tp_ledger_path": str(tp_path),
        "source_ledger_path": str(source_path),
        "gate_dir": str(gate_dir),
        "summary": summary,
        "gate_passed": bool(agg["gate"]["passed"]),
        "failed_checks": list(agg["gate"]["failed_checks"]),
        "trades": int(agg["trades"]),
        "win_rate": float(agg["selected_trade_win_rate"]),
        "total_bps": float(agg["notional_total_net_pnl_bps"]),
        "mean_bps": float(agg["notional_mean_net_pnl_bps"]),
        "min_trade_bps": float(agg["notional_min_trade_net_pnl_bps"]),
        "account_return_pct": float(agg["account_return_pct_no_compounding"]),
        "missed_trade_p05_account_return_pct": float(agg["missed_trade_p05_account_return_pct"]),
        "extra_cost_account_return_pct": float(agg["extra_cost_account_return_pct"]),
        "promoted_loss_min_account_return_pct": float(agg["promoted_loss_min_account_return_pct"]),
    }


def _write_report(payload: dict[str, object], summary: pd.DataFrame) -> None:
    lines = [
        "# Research V62 Holdout Entry Delay Results",
        "",
        "## Purpose",
        "",
        "V62 stress-tests the V60 design-selected sparse BTCUSDC rule on holdout folds only, varying entry delay without changing thresholds.",
        "",
        "Rule under audit: reversal, 1080m lookback, abs_return_bps q0.99, TP80, no stop loss, horizon reserve 1440m.",
        "",
        "## Summary",
        "",
        summary.to_markdown(index=False),
        "",
        "## Files",
        "",
        f"- Summary CSV: `{payload['summary_csv']}`",
        f"- Summary JSON: `{payload['summary_path']}`",
        "",
        "## Caveat",
        "",
        "This is holdout-only relative to the V60 selector split, but it is still historical BTCUSDC data. It does not replace future unseen validation.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    bars = _load_bars()
    runs = [_run_delay(bars, int(delay)) for delay in DELAYS]
    summary_rows = [
        {
            "entry_delay_min": row["entry_delay_min"],
            "gate_passed": row["gate_passed"],
            "trades": row["trades"],
            "win_rate": row["win_rate"],
            "total_bps": row["total_bps"],
            "mean_bps": row["mean_bps"],
            "min_trade_bps": row["min_trade_bps"],
            "account_return_pct": row["account_return_pct"],
            "missed_trade_p05_account_return_pct": row["missed_trade_p05_account_return_pct"],
            "extra_cost_account_return_pct": row["extra_cost_account_return_pct"],
            "promoted_loss_min_account_return_pct": row["promoted_loss_min_account_return_pct"],
            "failed_checks": ";".join(row["failed_checks"]),
        }
        for row in runs
    ]
    summary = pd.DataFrame(summary_rows)
    summary_csv = OUT_DIR / "v62_holdout_entry_delay_gate_summary.csv"
    summary.to_csv(summary_csv, index=False)
    payload: dict[str, object] = {
        "input_bars": str(INPUT_BARS),
        "bar_rows": int(len(bars)),
        "holdout_folds": sorted(HOLDOUT_FOLDS),
        "rule": RULE,
        "runs": runs,
        "summary_csv": str(summary_csv),
        "summary_path": str(OUT_DIR / "v62_summary.json"),
    }
    (OUT_DIR / "v62_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload, summary)
    print(json.dumps(payload, indent=2))
