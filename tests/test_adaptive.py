from __future__ import annotations

from pathlib import Path

from lob_microprice_lab.adaptive import run_adaptive_walk_forward
from lob_microprice_lab.sample_data import generate_sample_data


def test_adaptive_walk_forward_smoke(tmp_path: Path) -> None:
    book, trades = generate_sample_data(tmp_path / "data", rows=900, depth=5, seed=7)
    result = run_adaptive_walk_forward(
        book_path=book,
        trades_path=trades,
        base_config_path=None,
        out_dir=tmp_path / "adaptive",
        horizon_sec=1.0,
        threshold_bps=0.25,
        model_type="logistic",
        candidate_edges=[0.1, 0.3],
        cost_bps=0.5,
        latency_sec=0.0,
        folds=1,
        min_train_ratio=0.5,
        valid_ratio=0.2,
        calibration_ratio=0.2,
        min_calibration_trades=1,
        clean=True,
    )
    assert result["rows_dataset"] > 500
    assert (tmp_path / "adaptive" / "REPORT.md").exists()
