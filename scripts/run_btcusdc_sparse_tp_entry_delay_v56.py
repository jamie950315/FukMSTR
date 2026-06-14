from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_contract_lock import BTCUSDCContractPolicy, run_btcusdc_contract_lock
from lob_microprice_lab.btcusdc_sparse_tp import SparseTakeProfitPolicy, apply_take_profit_exit, build_sparse_abs_return_entries


ROOT = Path(__file__).resolve().parents[1]
INPUT_BARS = ROOT / "runs" / "research_v50_btcusdc_full_aggtrade_flow_input" / "btcusdc_full_aggtrade_1m_flow_bars.csv"
OUT_DIR = ROOT / "runs" / "research_v56_btcusdc_sparse_tp_entry_delay_stress"

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
    for col in ["open", "high", "low", "close", "volume", "signed_taker_imbalance"]:
        if col in bars.columns:
            bars[col] = pd.to_numeric(bars[col], errors="coerce")
    return bars


def _entries_for_delay(bars: pd.DataFrame, *, delay_minutes: int) -> pd.DataFrame:
    return build_sparse_abs_return_entries(
        bars,
        folds=FOLDS,
        entry_delay_minutes=int(delay_minutes),
        lookback_minutes=1440,
        horizon_minutes=1440,
        quantile=0.995,
    )


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


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bars = _load_bars()
    summaries: list[dict[str, object]] = []
    for delay in (1, 2, 5, 10, 15, 30, 60):
        entries = _entries_for_delay(bars, delay_minutes=delay)
        entries.to_csv(OUT_DIR / f"v56_delay{delay}_entries.csv", index=False)
        tp_ledger = apply_take_profit_exit(entries, bars, SparseTakeProfitPolicy(take_profit_bps=80.0, horizon_minutes=1440))
        tp_ledger["entry_delay_min"] = int(delay)
        tp_ledger.to_csv(OUT_DIR / f"v56_delay{delay}_tp80_ledger.csv", index=False)
        source_ledger = _to_contract_source_ledger(tp_ledger)
        source_path = OUT_DIR / f"v56_delay{delay}_source_ledger_for_contract_gate.csv"
        source_ledger.to_csv(source_path, index=False)
        result = run_btcusdc_contract_lock(
            v24_run_dir=ROOT / "runs" / "research_v24_btc_adaptive_exit_safety_lock",
            out_dir=ROOT / f"runs/research_v56_btcusdc_delay{delay}_contract_gate",
            policy=BTCUSDCContractPolicy(source_symbol=f"BTCUSDC V56 sparse TP80 entry delay {delay}m ledger"),
            btcusdc_ledger=source_path,
            data_start="2024-01-04",
            data_end="2026-06-10",
            clean=True,
        )
        agg = result["aggregate"]
        summaries.append(
            {
                "entry_delay_min": int(delay),
                "gate_passed": bool(agg["gate"]["passed"]),
                "trades": int(agg["trades"]),
                "win_rate": float(agg["selected_trade_win_rate"]),
                "total_bps": float(agg["notional_total_net_pnl_bps"]),
                "mean_bps": float(agg["notional_mean_net_pnl_bps"]),
                "min_trade_bps": float(agg["notional_min_trade_net_pnl_bps"]),
                "account_return_pct": float(agg["account_return_pct_no_compounding"]),
                "missed_trade_p05_account_return_pct": float(agg["missed_trade_p05_account_return_pct"]),
                "extra_cost_account_return_pct": float(agg["extra_cost_account_return_pct"]),
                "promoted_loss_min_account_return_pct": float(agg["promoted_loss_min_account_return_pct"]),
                "failed_checks": ";".join(agg["gate"]["failed_checks"]),
            }
        )

    summary = pd.DataFrame(summaries)
    summary.to_csv(OUT_DIR / "v56_entry_delay_gate_summary.csv", index=False)
    payload = {"runs": summaries}
    (OUT_DIR / "v56_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
