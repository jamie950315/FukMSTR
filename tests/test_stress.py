from __future__ import annotations

import numpy as np
import pandas as pd

from lob_microprice_lab.stress import (
    backtest_latency_non_overlapping,
    block_bootstrap_pnl,
    evaluate_robust_grid_gate,
    stress_sweep_predictions,
)


def _predictions() -> pd.DataFrame:
    ts = pd.date_range("2024-01-01", periods=40, freq="500ms", tz="UTC")
    mid = pd.Series(100.0 + 0.01 * np.arange(40))
    future = mid.shift(-4).fillna(mid.iloc[-1])
    return pd.DataFrame(
        {
            "timestamp": ts,
            "mid": mid,
            "future_mid": future,
            "future_return_bps": (future - mid) / mid * 10000.0,
            "label": 1,
            "pred_label": 1,
            "prob_down": 0.1,
            "prob_flat": 0.2,
            "prob_up": 0.7,
        }
    )


def test_latency_non_overlap_backtest_runs() -> None:
    frame, metrics = backtest_latency_non_overlapping(
        _predictions(), cost_bps=0.1, edge_threshold=0.3, horizon_sec=2.0, latency_sec=0.5
    )
    assert metrics["trades"] > 0
    assert "entry_mid_latency" in frame.columns
    assert metrics["mode"] == "latency_non_overlap"


def test_stress_sweep_and_grid_gate_run() -> None:
    sweep = stress_sweep_predictions(
        _predictions(), horizon_sec=2.0, cost_bps_values=[0.1, 0.2], latency_sec_values=[0.0], edge_thresholds=[0.3, 0.6]
    )
    assert len(sweep) == 4
    gate = evaluate_robust_grid_gate(sweep, min_trades=1)
    assert "passed" in gate
    assert gate["best_candidate"] is not None


def test_block_bootstrap_pnl_returns_quantiles() -> None:
    boot = block_bootstrap_pnl(pd.Series([1.0, -0.5, 2.0, 0.25]), iterations=50, block_size=2, seed=1)
    assert boot["trades"] == 4
    assert boot["mean_p95_bps"] >= boot["mean_p05_bps"]
