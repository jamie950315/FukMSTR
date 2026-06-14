from __future__ import annotations

import numpy as np
import pandas as pd

from lob_microprice_lab.execution import backtest_taker_bidask_non_overlapping, robust_profit_gate, sweep_taker_bidask
from lob_microprice_lab.ensemble import average_prediction_frames, select_stable_feature_columns


def _predictions() -> pd.DataFrame:
    ts = pd.date_range("2024-01-01", periods=30, freq="1s", tz="UTC")
    mid = 100.0 + 0.02 * np.arange(30)
    return pd.DataFrame(
        {
            "timestamp": ts,
            "best_bid": mid - 0.005,
            "best_ask": mid + 0.005,
            "mid": mid,
            "future_mid": np.roll(mid, -5),
            "future_return_bps": (np.roll(mid, -5) - mid) / mid * 10000,
            "label": 1,
            "pred_label": 1,
            "prob_down": 0.05,
            "prob_flat": 0.15,
            "prob_up": 0.8,
        }
    ).iloc[:-5].reset_index(drop=True)


def test_taker_bidask_non_overlap_runs() -> None:
    frame, metrics = backtest_taker_bidask_non_overlapping(
        _predictions(), cost_bps=0.1, edge_threshold=0.5, horizon_sec=5, latency_sec=1
    )
    assert metrics["mode"] == "taker_bidask_non_overlap"
    assert metrics["trades"] > 0
    assert "entry_px_taker" in frame.columns


def test_taker_sweep_gate_runs() -> None:
    sweep = sweep_taker_bidask(
        _predictions(), horizon_sec=5, cost_bps_values=[0.1], latency_sec_values=[0, 1], edge_thresholds=[0.5]
    )
    gate = robust_profit_gate(sweep, min_trades=1)
    assert len(sweep) == 2
    assert "passed" in gate


def test_average_prediction_frames_and_feature_selection() -> None:
    base = _predictions()
    p2 = base.copy()
    p2["prob_up"] = 0.6
    p2["prob_flat"] = 0.3
    p2["prob_down"] = 0.1
    avg = average_prediction_frames([base, p2])
    assert abs(float(avg.loc[0, "prob_up"]) - 0.7) < 1e-9
    f = pd.DataFrame({"future_return_bps": [1, 2, 3, 4], "a": [1, 2, 3, 4], "b": [4, 3, 2, 1], "c": [1, 1, 1, 1]})
    selected = select_stable_feature_columns(f, ["a", "b", "c"], top_k=2)
    assert len(selected) == 2
