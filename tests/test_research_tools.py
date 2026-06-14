import pandas as pd

from lob_microprice_lab.backtest import backtest_predictions_non_overlapping, sweep_edge_thresholds
from lob_microprice_lab.validation import make_walk_forward_folds


def test_non_overlap_backtest_reduces_overlapping_trades():
    predictions = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=6, freq="1s"),
            "future_return_bps": [2, 2, -2, 2, -2, 2],
            "prob_up": [0.8, 0.8, 0.2, 0.8, 0.2, 0.8],
            "prob_down": [0.1, 0.1, 0.7, 0.1, 0.7, 0.1],
            "prob_flat": [0.1] * 6,
        }
    )
    frame, metrics = backtest_predictions_non_overlapping(predictions, cost_bps=0.5, edge_threshold=0.3, horizon_sec=2.0)
    assert metrics["trades"] == 3.0
    assert frame["traded"].sum() == 3


def test_edge_sweep_outputs_event_and_non_overlap_modes():
    predictions = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=4, freq="1s"),
            "future_return_bps": [2, -2, 2, -2],
            "prob_up": [0.8, 0.1, 0.8, 0.1],
            "prob_down": [0.1, 0.8, 0.1, 0.8],
            "prob_flat": [0.1] * 4,
        }
    )
    sweep = sweep_edge_thresholds(predictions, cost_bps=0.5, thresholds=[0.3], horizon_sec=2.0)
    assert set(sweep["mode"]) == {"event", "non_overlap"}


def test_make_walk_forward_folds_uses_embargo():
    folds = make_walk_forward_folds(1000, folds=2, min_train_ratio=0.5, valid_ratio=0.2, embargo_rows=10)
    assert len(folds) == 2
    assert folds[0].train_end == folds[0].valid_start - 10
    assert folds[0].valid_rows == 200
