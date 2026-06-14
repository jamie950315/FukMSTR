from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from lob_microprice_lab.selective import (
    SelectiveCandidate,
    backtest_selective_taker_bidask_non_overlapping,
    build_selective_signals,
    run_selective_from_ensemble_dir,
)


def _pred_frame(rows: int = 12, trend: float = 1.0) -> pd.DataFrame:
    ts = pd.date_range("2024-01-01", periods=rows, freq="1s", tz="UTC")
    base = 100.0 + trend * pd.Series(range(rows), dtype=float) * 0.08
    return pd.DataFrame(
        {
            "timestamp": ts.astype(str),
            "best_bid": base,
            "best_ask": base + 0.01,
            "mid": base + 0.005,
            "prob_up": 0.9,
            "prob_down": 0.05,
            "prob_flat": 0.05,
            "spread_bps": 1.0,
            "imbalance_l3": 0.8,
            "mid_vol_60r_bps": 0.2,
            "label": 1,
        }
    )


def test_selective_rejects_future_filter() -> None:
    frame = _pred_frame()
    with pytest.raises(ValueError):
        build_selective_signals(frame, SelectiveCandidate(edge_threshold=0.5, signed_col="future_best_bid", signed_mode="agree"))


def test_selective_backtest_positive_on_monotone_fixture() -> None:
    frame = _pred_frame(rows=12, trend=1.0)
    candidate = SelectiveCandidate(edge_threshold=0.5, signed_col="imbalance_l3", signed_mode="agree", signed_abs_threshold=0.1)
    out, metrics = backtest_selective_taker_bidask_non_overlapping(frame, candidate=candidate, cost_bps=0.1, horizon_sec=2.0, latency_sec=0.0)
    assert metrics["trades"] > 0
    assert metrics["mean_net_pnl_bps"] > 0
    assert int(out["traded"].sum()) == int(metrics["trades"])


def test_selective_from_ensemble_dir(tmp_path: Path) -> None:
    source = tmp_path / "ensemble"
    fold = source / "fold_01"
    fold.mkdir(parents=True)
    _pred_frame(rows=24, trend=1.0).to_csv(fold / "calibration_predictions.csv", index=False)
    _pred_frame(rows=24, trend=1.0).to_csv(fold / "validation_predictions.csv", index=False)

    result = run_selective_from_ensemble_dir(
        ensemble_dir=source,
        out_dir=tmp_path / "selective",
        horizon_sec=2.0,
        cost_bps=0.1,
        latency_sec=0.0,
        edge_thresholds=[0.5],
        min_calibration_trades=1,
        stress_cost_bps_values=[0.1],
        stress_latency_sec_values=[0.0],
        clean=True,
    )
    assert result["aggregate"]["oof_trades"] > 0
    assert result["aggregate"]["oof_mean_net_pnl_bps"] > 0
    assert json.loads((tmp_path / "selective" / "fold_01" / "selected_candidate.json").read_text())["edge_threshold"] == 0.5
