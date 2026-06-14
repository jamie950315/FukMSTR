from __future__ import annotations

import numpy as np
import pandas as pd

from lob_microprice_lab.exit_lock import (
    ExitLockSpec,
    backtest_fixed_signals_taker_bidask_exit_lock,
    execution_path_arrays,
    fast_exit_lock_metrics,
)


def _toy_frame() -> pd.DataFrame:
    ts = pd.date_range("2020-01-01", periods=6, freq="1s", tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": ts.astype(str),
            "best_bid": [99.99, 100.40, 100.20, 100.10, 100.00, 100.00],
            "best_ask": [100.00, 100.42, 100.22, 100.12, 100.02, 100.02],
            "signal": [1, 1, 0, 0, 0, 0],
        }
    )


def test_take_profit_exit_reserves_original_horizon() -> None:
    frame = _toy_frame()
    spec = ExitLockSpec(take_profit_bps=30.0, stop_loss_bps=0.0, reserve_horizon=True)
    bt, metrics = backtest_fixed_signals_taker_bidask_exit_lock(
        frame,
        cost_bps=1.0,
        horizon_sec=3.0,
        latency_sec=0.0,
        spec=spec,
    )
    trades = bt[bt["traded"] == 1]
    assert len(trades) == 1
    assert trades.iloc[0]["exit_reason"] == "take_profit"
    assert trades.iloc[0]["hold_sec"] == 1.0
    assert metrics["take_profit_exits"] == 1.0
    assert metrics["horizon_exits"] == 0.0
    # Entry at ask 100.00, exit at bid 100.40 = 40 bps gross, less 1 bp cost.
    assert abs(float(trades.iloc[0]["net_pnl_bps"]) - 39.0) < 1e-9


def test_fast_exit_lock_metrics_matches_materialized_backtest() -> None:
    frame = _toy_frame()
    spec = ExitLockSpec(take_profit_bps=30.0, stop_loss_bps=0.0, reserve_horizon=True)
    arrays = execution_path_arrays(frame, horizon_sec=3.0, latency_sec=0.0)
    fast_metrics, pnl, reasons, holds = fast_exit_lock_metrics(
        frame["signal"].to_numpy(dtype=int),
        arrays,
        cost_bps=1.0,
        spec=spec,
    )
    bt, slow_metrics = backtest_fixed_signals_taker_bidask_exit_lock(
        frame,
        cost_bps=1.0,
        horizon_sec=3.0,
        latency_sec=0.0,
        spec=spec,
    )
    assert np.allclose(pnl, bt.loc[bt["traded"] == 1, "net_pnl_bps"].to_numpy())
    assert reasons == ["take_profit"]
    assert np.allclose(holds, [1.0])
    assert fast_metrics["total_net_pnl_bps"] == slow_metrics["total_net_pnl_bps"]
