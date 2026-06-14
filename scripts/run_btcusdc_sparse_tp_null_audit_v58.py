from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from lob_microprice_lab.btcusdc_contract_lock import BTCUSDCContractPolicy, run_btcusdc_contract_lock
from lob_microprice_lab.btcusdc_sparse_tp import (
    SparseTakeProfitPolicy,
    apply_take_profit_exit,
    build_direction_flip_entries,
    build_sparse_abs_return_entries,
    summarize_sparse_tp_outcomes,
)


ROOT = Path(__file__).resolve().parents[1]
INPUT_BARS = ROOT / "runs" / "research_v48_btcusdc_full_1m_direct_ml_input" / "btcusdc_full_1m_bars.csv"
OUT_DIR = ROOT / "runs" / "research_v58_btcusdc_sparse_tp_null_audit"
FLIP_GATE_DIR = ROOT / "runs" / "research_v58_btcusdc_direction_flip_contract_gate"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V58_NULL_AUDIT_RESULTS.md"

NULL_RUNS = 2000
NULL_SEED = 580058
QUOTE_SURCHARGE_BPS = 0.5

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


def _bar_cache(bars: pd.DataFrame) -> dict[str, object]:
    timestamps = pd.to_datetime(bars["timestamp"], utc=True).reset_index(drop=True)
    return {
        "timestamps": timestamps,
        "open": bars["open"].to_numpy(dtype=float),
        "high": bars["high"].to_numpy(dtype=float),
        "low": bars["low"].to_numpy(dtype=float),
    }


def _validation_indices(bars: pd.DataFrame) -> dict[int, np.ndarray]:
    out: dict[int, np.ndarray] = {}
    ts = pd.to_datetime(bars["timestamp"], utc=True)
    max_idx = len(bars) - 1
    for fold, _, _, validation_start, validation_end in FOLDS:
        start = pd.Timestamp(validation_start, tz="UTC")
        end = pd.Timestamp(validation_end, tz="UTC")
        idx = np.flatnonzero(((ts >= start) & (ts < end)).to_numpy(bool))
        out[int(fold)] = idx[idx + 1440 <= max_idx]
    return out


def _apply_tp_exit_cached(entries: pd.DataFrame, cache: dict[str, object], policy: SparseTakeProfitPolicy) -> pd.DataFrame:
    timestamps = cache["timestamps"]
    open_values = cache["open"]
    high_values = cache["high"]
    low_values = cache["low"]
    rows: list[dict[str, object]] = []
    max_idx = len(open_values) - 1
    for _, row in entries.iterrows():
        entry_idx = int(row["idx"])
        signal = int(row["signal"])
        entry_px = float(row["entry_px"])
        horizon_idx = min(entry_idx + int(policy.horizon_minutes), max_idx)
        exit_idx = horizon_idx
        exit_px = float(open_values[horizon_idx])
        exit_reason = "horizon"
        gross_pnl_bps = (exit_px / entry_px - 1.0) * 10000.0 * signal
        tp_px = entry_px * (1.0 + signal * float(policy.take_profit_bps) / 10000.0)
        for idx in range(entry_idx + 1, horizon_idx + 1):
            hit = float(high_values[idx]) >= tp_px if signal == 1 else float(low_values[idx]) <= tp_px
            if hit:
                exit_idx = idx
                exit_px = tp_px
                exit_reason = "take_profit"
                gross_pnl_bps = float(policy.take_profit_bps)
                break
        out = row.to_dict()
        out.update(
            {
                "tp_bps": float(policy.take_profit_bps),
                "exit_idx": int(exit_idx),
                "exit_timestamp": timestamps.iloc[exit_idx],
                "exit_px": float(exit_px),
                "exit_reason": exit_reason,
                "gross_pnl_bps": float(gross_pnl_bps),
                "cost_bps": float(policy.taker_roundtrip_fee_bps),
                "net_pnl_bps": float(gross_pnl_bps) - float(policy.taker_roundtrip_fee_bps),
                "hold_sec": float((timestamps.iloc[exit_idx] - pd.Timestamp(row["timestamp"])).total_seconds()),
            }
        )
        rows.append(out)
    return pd.DataFrame(rows)


def _sample_null_entries_cached(
    entries: pd.DataFrame,
    cache: dict[str, object],
    valid_indices: dict[int, np.ndarray],
    *,
    seed: int,
    run_id: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(int(seed))
    timestamps = cache["timestamps"]
    open_values = cache["open"]
    rows: list[dict[str, object]] = []
    for fold, group in entries.groupby("fold", sort=True):
        candidates = valid_indices[int(fold)]
        horizon = int(pd.to_numeric(group.get("horizon_minutes", pd.Series([1440])), errors="coerce").dropna().iloc[0])
        sampled: list[int] = []
        for _ in range(10000):
            candidate = int(rng.choice(candidates))
            if all(abs(candidate - kept) >= horizon for kept in sampled):
                sampled.append(candidate)
                if len(sampled) == len(group):
                    break
        if len(sampled) < len(group):
            raise ValueError(f"could not sample non-overlapping null candidates for fold {int(fold)}")
        template = group.reset_index(drop=True)
        for row_number, bar_idx in enumerate(sorted(sampled)):
            template_row = template.iloc[row_number].to_dict()
            entry_delay = int(template_row.get("entry_delay_min", 1))
            entry_ts = timestamps.iloc[int(bar_idx)]
            template_row.update(
                {
                    "signal_idx": int(bar_idx) - entry_delay,
                    "idx": int(bar_idx),
                    "signal_timestamp": entry_ts - pd.Timedelta(minutes=entry_delay),
                    "timestamp": entry_ts,
                    "replay_date": str(entry_ts.date()),
                    "entry_px": float(open_values[int(bar_idx)]),
                    "direction": "random_time_null",
                    "null_run": int(run_id),
                }
            )
            rows.append(template_row)
    return pd.DataFrame(rows)


def _quantiles(values: pd.Series) -> dict[str, float]:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return {"p01": 0.0, "p05": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
    return {
        "p01": float(numeric.quantile(0.01)),
        "p05": float(numeric.quantile(0.05)),
        "p50": float(numeric.quantile(0.50)),
        "p95": float(numeric.quantile(0.95)),
        "p99": float(numeric.quantile(0.99)),
        "max": float(numeric.max()),
    }


def _write_report(payload: dict[str, object]) -> None:
    observed = payload["observed_summary"]
    flip = payload["direction_flip_summary"]
    null = payload["random_null"]
    flip_gate = payload["direction_flip_gate"]["aggregate"]["gate"]
    lines = [
        "# Research V58 Null Audit Results",
        "",
        "## Purpose",
        "",
        "V58 audits whether the fixed V55/V57 sparse BTCUSDC TP80 result is easily reproduced by simple negative controls.",
        "",
        "Frozen rule under audit: lookback 1440m, horizon reserve 1440m, reversal direction, abs_return_bps q0.995 per fold calibration window, next-open entry, TP80, no stop loss.",
        "",
        "## Observed Kline Baseline",
        "",
        f"- Trades: `{observed['trades']}`",
        f"- Wins: `{observed['wins']}`",
        f"- Win rate: `{float(observed['win_rate']):.6f}`",
        f"- Total net pnl after BTCUSDC surcharge: `{float(observed['total_net_pnl_bps']):.6f}` bps",
        f"- Min trade net pnl after BTCUSDC surcharge: `{float(observed['min_trade_net_pnl_bps']):.6f}` bps",
        "",
        "## Direction Flip Control",
        "",
        f"- Gate passed: `{bool(flip_gate['passed'])}`",
        f"- Failed checks: `{';'.join(flip_gate['failed_checks']) if flip_gate['failed_checks'] else ''}`",
        f"- Trades: `{flip['trades']}`",
        f"- Wins: `{flip['wins']}`",
        f"- Win rate: `{float(flip['win_rate']):.6f}`",
        f"- Total net pnl after BTCUSDC surcharge: `{float(flip['total_net_pnl_bps']):.6f}` bps",
        f"- Min trade net pnl after BTCUSDC surcharge: `{float(flip['min_trade_net_pnl_bps']):.6f}` bps",
        "",
        "## Random Time Null",
        "",
        f"- Runs: `{null['runs']}`",
        f"- Seed: `{null['seed']}`",
        f"- P(null wins >= observed wins): `{float(null['p_wins_ge_observed']):.6f}`",
        f"- P(null total pnl >= observed total pnl): `{float(null['p_total_ge_observed']):.6f}`",
        f"- P(null wins and total pnl both >= observed): `{float(null['p_joint_ge_observed']):.6f}`",
        f"- Null wins quantiles: `{null['wins_quantiles']}`",
        f"- Null total pnl quantiles: `{null['total_net_pnl_bps_quantiles']}`",
        "",
        "## Files",
        "",
        f"- Observed entries: `{payload['observed_entries_path']}`",
        f"- Direction flip ledger: `{payload['direction_flip_ledger_path']}`",
        f"- Direction flip gate directory: `{payload['direction_flip_gate_dir']}`",
        f"- Random null summary: `{payload['random_null_summary_path']}`",
        f"- Summary JSON: `{payload['summary_path']}`",
        "",
        "## Caveat",
        "",
        "This is a negative-control audit. It strengthens or weakens the current sparse rule evidence, but it does not create more observed trades or prove future performance.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    bars = _load_bars()
    cache = _bar_cache(bars)
    valid_indices = _validation_indices(bars)
    observed_entries = build_sparse_abs_return_entries(
        bars,
        folds=FOLDS,
        entry_delay_minutes=1,
        lookback_minutes=1440,
        horizon_minutes=1440,
        quantile=0.995,
    )
    observed_entries_path = OUT_DIR / "v58_observed_kline_entries.csv"
    observed_entries.to_csv(observed_entries_path, index=False)

    policy = SparseTakeProfitPolicy(take_profit_bps=80.0, horizon_minutes=1440)
    observed_ledger = _apply_tp_exit_cached(observed_entries, cache, policy)
    observed_ledger_path = OUT_DIR / "v58_observed_kline_tp80_ledger.csv"
    observed_ledger.to_csv(observed_ledger_path, index=False)
    observed_summary = summarize_sparse_tp_outcomes(observed_ledger, quote_surcharge_bps=QUOTE_SURCHARGE_BPS)

    flip_entries = build_direction_flip_entries(observed_entries)
    flip_entries_path = OUT_DIR / "v58_direction_flip_entries.csv"
    flip_entries.to_csv(flip_entries_path, index=False)
    flip_ledger = _apply_tp_exit_cached(flip_entries, cache, policy)
    flip_ledger_path = OUT_DIR / "v58_direction_flip_tp80_ledger.csv"
    flip_ledger.to_csv(flip_ledger_path, index=False)
    flip_summary = summarize_sparse_tp_outcomes(flip_ledger, quote_surcharge_bps=QUOTE_SURCHARGE_BPS)
    flip_source_path = OUT_DIR / "v58_direction_flip_source_ledger_for_contract_gate.csv"
    _to_contract_source_ledger(flip_ledger).to_csv(flip_source_path, index=False)
    flip_gate = run_btcusdc_contract_lock(
        v24_run_dir=ROOT / "runs" / "research_v24_btc_adaptive_exit_safety_lock",
        out_dir=FLIP_GATE_DIR,
        policy=BTCUSDCContractPolicy(source_symbol="BTCUSDC V58 direction-flip sparse TP80 null ledger"),
        btcusdc_ledger=flip_source_path,
        data_start="2024-01-04",
        data_end="2026-06-10",
        clean=True,
    )

    null_rows: list[dict[str, object]] = []
    for run in range(int(NULL_RUNS)):
        null_entries = _sample_null_entries_cached(
            observed_entries,
            cache,
            valid_indices,
            seed=int(NULL_SEED) + int(run),
            run_id=int(run),
        )
        null_ledger = _apply_tp_exit_cached(null_entries, cache, policy)
        row = summarize_sparse_tp_outcomes(null_ledger, quote_surcharge_bps=QUOTE_SURCHARGE_BPS)
        row["run"] = int(run)
        null_rows.append(row)
    null_summary = pd.DataFrame(null_rows)
    null_summary_path = OUT_DIR / "v58_random_time_null_summary.csv"
    null_summary.to_csv(null_summary_path, index=False)

    observed_wins = int(observed_summary["wins"])
    observed_total = float(observed_summary["total_net_pnl_bps"])
    null_wins = pd.to_numeric(null_summary["wins"], errors="coerce")
    null_total = pd.to_numeric(null_summary["total_net_pnl_bps"], errors="coerce")
    random_null = {
        "runs": int(len(null_summary)),
        "seed": int(NULL_SEED),
        "p_wins_ge_observed": float((null_wins >= observed_wins).mean()),
        "p_total_ge_observed": float((null_total >= observed_total).mean()),
        "p_joint_ge_observed": float(((null_wins >= observed_wins) & (null_total >= observed_total)).mean()),
        "wins_quantiles": _quantiles(null_wins),
        "total_net_pnl_bps_quantiles": _quantiles(null_total),
    }

    payload: dict[str, object] = {
        "input_bars": str(INPUT_BARS),
        "bar_rows": int(len(bars)),
        "observed_entries_path": str(observed_entries_path),
        "observed_ledger_path": str(observed_ledger_path),
        "observed_summary": observed_summary,
        "direction_flip_entries_path": str(flip_entries_path),
        "direction_flip_ledger_path": str(flip_ledger_path),
        "direction_flip_source_ledger_path": str(flip_source_path),
        "direction_flip_gate_dir": str(FLIP_GATE_DIR),
        "direction_flip_summary": flip_summary,
        "direction_flip_gate": flip_gate,
        "random_null_summary_path": str(null_summary_path),
        "random_null": random_null,
        "summary_path": str(OUT_DIR / "v58_summary.json"),
    }
    (OUT_DIR / "v58_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload)
    print(json.dumps(payload, indent=2))
