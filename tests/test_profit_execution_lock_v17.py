from __future__ import annotations

from pathlib import Path

import pandas as pd

from lob_microprice_lab.exit_lock import ExitLockSpec
from lob_microprice_lab.kline_guard import KlineGuardSpec
from lob_microprice_lab.profit_execution_lock import ExecutionProfitLockGate, run_execution_profit_lock_certificate


def _toy_predictions(rows: int = 24) -> pd.DataFrame:
    ts = pd.date_range("2020-01-01", periods=rows, freq="1s", tz="UTC")
    mid = 100.0 + 0.05 * pd.Series(range(rows), dtype=float)
    return pd.DataFrame(
        {
            "timestamp": ts.astype(str),
            "best_bid": mid - 0.01,
            "best_ask": mid + 0.01,
            "prob_down": 0.1,
            "prob_flat": 0.1,
            "prob_up": 0.8,
            "ofi_sum_l5_norm": 0.0,
            "kline_15s_rv_6_bps": 1.0,
        }
    )


def _write_fold(root: Path, fold: int, split: str, frame: pd.DataFrame, *, is_kline: bool) -> None:
    d = root / f"fold_{fold:02d}"
    d.mkdir(parents=True, exist_ok=True)
    cols = ["timestamp", "prob_down", "prob_flat", "prob_up", "ofi_sum_l5_norm", "kline_15s_rv_6_bps"]
    if is_kline:
        cols = ["timestamp", "best_bid", "best_ask", "prob_down", "prob_flat", "prob_up", "ofi_sum_l5_norm", "kline_15s_rv_6_bps"]
    frame[cols].to_csv(d / f"{split}_predictions.csv", index=False)


def test_execution_profit_lock_certificate_writes_outputs(tmp_path: Path) -> None:
    base = tmp_path / "base"
    kline = tmp_path / "kline"
    for split in ["calibration", "validation"]:
        frame = _toy_predictions()
        _write_fold(base, 1, split, frame, is_kline=False)
        _write_fold(kline, 1, split, frame, is_kline=True)

    out = tmp_path / "out"
    result = run_execution_profit_lock_certificate(
        base_ensemble_dir=base,
        kline_ensemble_dir=kline,
        out_dir=out,
        horizon_sec=3.0,
        cost_bps=1.0,
        latency_sec=0.0,
        selected_signal_spec=KlineGuardSpec(
            edge_threshold=0.1,
            kline_alpha=0.125,
            ofi_col="ofi_sum_l5_norm",
            ofi_quantile=0.9,
            kline_col="kline_15s_rv_6_bps",
            kline_quantile=0.0,
            kline_operator=">=",
            directional=True,
        ),
        selected_exit_spec=ExitLockSpec(take_profit_bps=8.0, stop_loss_bps=0.0, reserve_horizon=True),
        alpha_grid=[0.125],
        ofi_cols=["ofi_sum_l5_norm"],
        ofi_quantiles=[0.9],
        kline_cols=["kline_15s_rv_6_bps"],
        kline_quantiles=[0.0],
        exit_take_profit_bps_values=[0.0, 8.0],
        exit_stop_loss_bps_values=[0.0],
        stress_cost_bps_values=[1.0],
        stress_latency_sec_values=[0.0],
        shift_null_runs=1,
        gate=ExecutionProfitLockGate(
            min_oof_trades=1,
            min_folds_with_trades=1,
            min_fold_mean_net_bps=-1e9,
            min_fold_total_net_bps=-1e9,
            min_bootstrap_mean_p05_bps=-1e9,
            max_addone_family_p=1.0,
            min_top_winner_removal_k=1,
            min_top_winner_removed_total_bps=-1e9,
            min_full_stress_mean_net_bps=-1e9,
            min_full_stress_total_net_bps=-1e9,
            min_equal_trade_blocks_5_positive=0,
            min_equal_trade_blocks_10_positive=0,
        ),
        clean=True,
    )
    assert result["aggregate"]["trades"] >= 1
    assert (out / "summary.json").exists()
    assert (out / "execution_lock_oof_backtest.csv").exists()
    assert (out / "execution_lock_sparse_family_shift_null.csv").exists()
