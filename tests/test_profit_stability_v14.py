import math

import numpy as np
import pandas as pd

from lob_microprice_lab.profit_stability import (
    _fast_signal_metrics,
    _prepare_execution_arrays,
    summarize_trade_stability,
)
from lob_microprice_lab.selective import backtest_fixed_signals_taker_bidask_non_overlapping


def test_fast_signal_metrics_matches_reference_backtest():
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2020-01-01", periods=8, freq="1s", tz="UTC"),
            "best_bid": [100.0, 100.5, 101.0, 101.5, 101.0, 100.5, 100.0, 99.5],
            "best_ask": [100.1, 100.6, 101.1, 101.6, 101.1, 100.6, 100.1, 99.6],
            "signal": [1, 1, -1, 0, -1, 1, 0, 0],
        }
    )
    ref, ref_metrics = backtest_fixed_signals_taker_bidask_non_overlapping(
        frame,
        cost_bps=1.5,
        horizon_sec=2.0,
        latency_sec=0.0,
    )
    arrays = _prepare_execution_arrays(frame, horizon_sec=2.0, latency_sec=0.0)
    fast_metrics, pnls = _fast_signal_metrics(frame["signal"].to_numpy(dtype=int), arrays, cost_bps=1.5)
    assert int(fast_metrics["trades"]) == int(ref_metrics["trades"])
    assert math.isclose(fast_metrics["total_net_pnl_bps"], ref_metrics["total_net_pnl_bps"], rel_tol=1e-12, abs_tol=1e-12)
    assert math.isclose(fast_metrics["mean_net_pnl_bps"], ref_metrics["mean_net_pnl_bps"], rel_tol=1e-12, abs_tol=1e-12)
    np.testing.assert_allclose(pnls, ref.loc[ref["traded"] == 1, "net_pnl_bps"].to_numpy())


def test_summarize_trade_stability_equal_blocks_and_loo():
    frame = pd.DataFrame(
        {
            "traded": [1, 1, 1, 1, 1, 1],
            "net_pnl_bps": [5.0, 4.0, 3.0, 2.0, 1.0, 1.5],
            "fold": [1, 1, 2, 2, 3, 3],
        }
    )
    summary = summarize_trade_stability(frame, equal_trade_blocks=3)
    assert summary["equal_trade_block_count"] == 3
    assert summary["positive_equal_trade_blocks"] == 3
    assert math.isclose(summary["equal_trade_block_min_total_bps"], 2.5)
    assert math.isclose(summary["leave_one_fold_out_min_total_bps"], 7.5)
