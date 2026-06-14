from __future__ import annotations

from pathlib import Path

import yaml

from lob_microprice_lab.pipeline import run_train
from lob_microprice_lab.sample_data import generate_sample_data


def test_run_train_end_to_end(tmp_path: Path):
    data_dir = tmp_path / "data"
    run_dir = tmp_path / "run"
    book_path, trades_path = generate_sample_data(data_dir, rows=220, depth=5, seed=3)
    cfg_path = tmp_path / "config.yaml"
    cfg = {
        "features": {
            "depth_levels": [1, 3, 5],
            "trade_windows_sec": [1.0],
            "add_lagged_features": True,
            "ewm_span": 8,
            "add_order_flow_features": False,
            "add_depth_shape_features": False,
            "add_multi_level_microprice": False,
            "temporal_windows_rows": [2, 5],
        },
        "labels": {"horizon_sec": 1.0, "threshold_bps": 0.5},
        "split": {"train_ratio": 0.7},
        "model": {"type": "hgb", "random_state": 7, "max_iter": 40, "quantile_clip": [0.01, 0.99]},
        "backtest": {"cost_bps": 1.5, "signal_edge_threshold": 0.1},
        "io": {"timestamp_col": "timestamp"},
    }
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    summary = run_train(book_path, trades_path, cfg_path, run_dir)

    assert summary["rows_total"] > 150
    assert summary["feature_count"] > 20
    assert (run_dir / "model.joblib").exists()
    assert (run_dir / "predictions_valid.csv").exists()
    assert (run_dir / "metrics.json").exists()
    assert (run_dir / "probability_metrics.json").exists()
    assert (run_dir / "backtest_non_overlap.json").exists()
    assert (run_dir / "edge_sweep.csv").exists()
