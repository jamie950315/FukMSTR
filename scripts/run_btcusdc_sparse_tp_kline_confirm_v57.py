from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_contract_lock import BTCUSDCContractPolicy, run_btcusdc_contract_lock
from lob_microprice_lab.btcusdc_sparse_tp import SparseTakeProfitPolicy, apply_take_profit_exit, build_sparse_abs_return_entries


ROOT = Path(__file__).resolve().parents[1]
INPUT_BARS = ROOT / "runs" / "research_v48_btcusdc_full_1m_direct_ml_input" / "btcusdc_full_1m_bars.csv"
V55_ENTRIES = ROOT / "runs" / "research_v55_btcusdc_sparse_tp_next_open_causal" / "v55_next_open_entries.csv"
OUT_DIR = ROOT / "runs" / "research_v57_btcusdc_sparse_tp_kline_confirm"
GATE_DIR = ROOT / "runs" / "research_v57_btcusdc_sparse_tp_kline_confirm_contract_gate"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V57_KLINE_CONFIRM_RESULTS.md"

FOLDS = (
    (1, "2024-01-05", "2025-04-04", "2025-04-04", "2025-06-03"),
    (2, "2024-03-05", "2025-06-03", "2025-06-03", "2025-08-02"),
    (3, "2024-05-04", "2025-08-02", "2025-08-02", "2025-10-01"),
    (4, "2024-07-03", "2025-10-01", "2025-10-01", "2025-11-30"),
    (5, "2024-09-01", "2025-11-30", "2025-11-30", "2026-01-29"),
    (6, "2024-10-31", "2026-01-29", "2026-01-29", "2026-03-30"),
    (7, "2024-12-30", "2026-03-30", "2026-03-30", "2026-05-29"),
)


def _load_bars() -> pd.DataFrame:
    bars = pd.read_csv(INPUT_BARS, parse_dates=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    for col in ["open", "high", "low", "close", "volume"]:
        bars[col] = pd.to_numeric(bars[col], errors="coerce")
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars["replay_date"] = bars["timestamp"].dt.date.astype(str)
    return bars


def _to_contract_source_ledger(tp_ledger: pd.DataFrame) -> pd.DataFrame:
    source = pd.DataFrame(
        {
            "timestamp": tp_ledger["timestamp"],
            "best_bid": tp_ledger["entry_px"],
            "best_ask": tp_ledger["entry_px"],
            "signal": tp_ledger["signal"].astype(int),
            "fold": tp_ledger["fold"].astype(int),
            "raw_selective_signal": tp_ledger["signal"].astype(int),
            "traded": 1,
            "entry_px_taker": tp_ledger["entry_px"],
            "exit_px_taker": tp_ledger["exit_px"],
            "latency_sec": tp_ledger["entry_delay_min"].astype(float) * 60.0,
            "gross_pnl_bps": tp_ledger["gross_pnl_bps"],
            "cost_bps": tp_ledger["cost_bps"],
            "net_pnl_bps": tp_ledger["net_pnl_bps"],
            "exit_reason": tp_ledger["exit_reason"],
            "hold_sec": tp_ledger["hold_sec"],
            "take_profit_bps": tp_ledger["tp_bps"],
            "stop_loss_bps": 0.0,
            "reserve_horizon": True,
            "replay_date": tp_ledger["replay_date"],
            "threshold": tp_ledger["threshold"],
            "lookback_minutes": tp_ledger["lookback_minutes"],
            "horizon_minutes": tp_ledger["horizon_minutes"],
            "filter_feature": tp_ledger["filter_feature"],
            "quantile": tp_ledger["quantile"],
        }
    )
    source["equity_bps"] = pd.to_numeric(source["net_pnl_bps"], errors="coerce").fillna(0.0).cumsum()
    return source


def _compare_with_v55(kline_entries: pd.DataFrame) -> dict[str, object]:
    if not V55_ENTRIES.exists():
        return {"v55_entries_path": str(V55_ENTRIES), "available": False}

    v55 = pd.read_csv(V55_ENTRIES, parse_dates=["signal_timestamp", "timestamp"])
    for frame in (v55, kline_entries):
        frame["signal_timestamp"] = pd.to_datetime(frame["signal_timestamp"], utc=True)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)

    key_cols = ["fold", "signal_timestamp", "timestamp", "signal"]
    left = kline_entries[key_cols + ["entry_px", "threshold"]].rename(columns={"entry_px": "kline_entry_px", "threshold": "kline_threshold"})
    right = v55[key_cols + ["entry_px", "threshold"]].rename(columns={"entry_px": "aggtrade_entry_px", "threshold": "aggtrade_threshold"})
    merged = left.merge(right, on=key_cols, how="outer", indicator=True)
    merged.to_csv(OUT_DIR / "v57_kline_vs_v55_entry_comparison.csv", index=False)

    matched = merged.loc[merged["_merge"] == "both"].copy()
    if matched.empty:
        max_entry_px_diff = None
        max_threshold_diff = None
    else:
        max_entry_px_diff = float((pd.to_numeric(matched["kline_entry_px"]) - pd.to_numeric(matched["aggtrade_entry_px"])).abs().max())
        max_threshold_diff = float((pd.to_numeric(matched["kline_threshold"]) - pd.to_numeric(matched["aggtrade_threshold"])).abs().max())

    return {
        "v55_entries_path": str(V55_ENTRIES),
        "available": True,
        "v55_entries": int(len(v55)),
        "kline_entries": int(len(kline_entries)),
        "matched_entries": int((merged["_merge"] == "both").sum()),
        "kline_only_entries": int((merged["_merge"] == "left_only").sum()),
        "v55_only_entries": int((merged["_merge"] == "right_only").sum()),
        "max_entry_px_abs_diff": max_entry_px_diff,
        "max_threshold_abs_diff": max_threshold_diff,
    }


def _write_report(payload: dict[str, object]) -> None:
    agg = payload["aggregate"]
    gate = agg["gate"]
    comparison = payload["v55_comparison"]
    lines = [
        "# Research V57 Kline Confirmation Results",
        "",
        "## Purpose",
        "",
        "V57 reruns the fixed V55 sparse BTCUSDC rule on Binance public 1m kline bars instead of aggTrade-derived 1m bars.",
        "",
        "Frozen rule: lookback 1440m, horizon reserve 1440m, reversal direction, abs_return_bps q0.995 per fold calibration window, next-open entry, TP80, no stop loss.",
        "",
        "## Result",
        "",
        f"- Gate passed: `{bool(gate['passed'])}`",
        f"- Trades: `{int(agg['trades'])}`",
        f"- Win rate: `{float(agg['selected_trade_win_rate']):.6f}`",
        f"- Total net pnl: `{float(agg['notional_total_net_pnl_bps']):.6f}` bps",
        f"- Mean net pnl: `{float(agg['notional_mean_net_pnl_bps']):.6f}` bps",
        f"- Min trade net pnl: `{float(agg['notional_min_trade_net_pnl_bps']):.6f}` bps",
        f"- 8x account return: `{float(agg['account_return_pct_no_compounding']):.6f}%`",
        f"- Failed checks: `{';'.join(gate['failed_checks']) if gate['failed_checks'] else ''}`",
        "",
        "## V55 Entry Comparison",
        "",
        f"- V55 comparison available: `{bool(comparison.get('available'))}`",
        f"- Matched entries: `{comparison.get('matched_entries')}`",
        f"- Kline-only entries: `{comparison.get('kline_only_entries')}`",
        f"- V55-only entries: `{comparison.get('v55_only_entries')}`",
        f"- Max entry price absolute diff: `{comparison.get('max_entry_px_abs_diff')}`",
        f"- Max threshold absolute diff: `{comparison.get('max_threshold_abs_diff')}`",
        "",
        "## Files",
        "",
        f"- Entries: `{payload['entries_path']}`",
        f"- TP ledger: `{payload['tp_ledger_path']}`",
        f"- Contract source ledger: `{payload['source_ledger_path']}`",
        f"- Gate directory: `{payload['gate_dir']}`",
        f"- Summary JSON: `{payload['summary_path']}`",
        "",
        "## Caveat",
        "",
        "This confirms the fixed sparse rule on a second public 1m OHLC source. It does not remove the small sample-size risk: the result still has only 11 trades.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    bars = _load_bars()
    entries = build_sparse_abs_return_entries(
        bars,
        folds=FOLDS,
        entry_delay_minutes=1,
        lookback_minutes=1440,
        horizon_minutes=1440,
        quantile=0.995,
    )
    entries_path = OUT_DIR / "v57_kline_next_open_entries.csv"
    entries.to_csv(entries_path, index=False)

    tp_ledger = apply_take_profit_exit(entries, bars, SparseTakeProfitPolicy(take_profit_bps=80.0, horizon_minutes=1440))
    tp_ledger_path = OUT_DIR / "v57_kline_next_open_tp80_ledger.csv"
    tp_ledger.to_csv(tp_ledger_path, index=False)

    source_ledger = _to_contract_source_ledger(tp_ledger)
    source_path = OUT_DIR / "v57_kline_next_open_tp80_source_ledger_for_contract_gate.csv"
    source_ledger.to_csv(source_path, index=False)

    result = run_btcusdc_contract_lock(
        v24_run_dir=ROOT / "runs" / "research_v24_btc_adaptive_exit_safety_lock",
        out_dir=GATE_DIR,
        policy=BTCUSDCContractPolicy(source_symbol="BTCUSDC V57 sparse reversal abs-return TP80 next-open public kline ledger"),
        btcusdc_ledger=source_path,
        data_start="2024-01-04",
        data_end="2026-06-10",
        clean=True,
    )

    payload: dict[str, object] = {
        "input_bars": str(INPUT_BARS),
        "bar_rows": int(len(bars)),
        "bar_start": str(bars["timestamp"].iloc[0]) if not bars.empty else None,
        "bar_end": str(bars["timestamp"].iloc[-1]) if not bars.empty else None,
        "entries_path": str(entries_path),
        "tp_ledger_path": str(tp_ledger_path),
        "source_ledger_path": str(source_path),
        "gate_dir": str(GATE_DIR),
        "summary_path": str(OUT_DIR / "v57_summary.json"),
        "entries": int(len(entries)),
        "v55_comparison": _compare_with_v55(entries),
        "aggregate": result["aggregate"],
    }
    (OUT_DIR / "v57_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload)
    print(json.dumps(payload, indent=2))
