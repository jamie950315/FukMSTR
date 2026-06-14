from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.long_horizon import LongWindowGateConfig, gate_long_window_candidate, parse_model_sets, summarize_completed_long_runs


def test_parse_model_sets() -> None:
    assert parse_model_sets("logistic;logistic,hgb") == [["logistic"], ["logistic", "hgb"]]


def test_gate_long_window_candidate_passes_positive_run() -> None:
    folds = pd.DataFrame(
        {
            "valid_trades": [12, 11, 13],
            "valid_mean_net_pnl_bps": [2.0, 1.5, 3.0],
            "bootstrap_mean_p05_bps": [0.2, 0.1, 0.5],
        }
    )
    summary = {
        "aggregate": {"oof_trades": 36, "oof_mean_net_pnl_bps": 2.2, "oof_total_net_pnl_bps": 79.2, "oof_hit_rate": 0.7},
        "profit_gate": {"passed": True, "best_candidate": {"min_mean_net_pnl_bps": 0.5, "min_total_net_pnl_bps": 20.0}},
    }
    gate = gate_long_window_candidate(fold_metrics=folds, stress_sweep=pd.DataFrame(), summary=summary, cfg=LongWindowGateConfig())
    assert gate["v06_long_window_pass"] is True
    assert gate["fold_trades_min"] == 11.0


def test_summarize_completed_long_runs(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    (run / "summary.json").write_text(
        json.dumps(
            {
                "horizon_sec": 45.0,
                "models": ["logistic"],
                "top_k_features": 80,
                "threshold_bps": 1.0,
                "cost_bps": 1.5,
                "latency_sec": 0.5,
                "aggregate": {"oof_trades": 31, "oof_mean_net_pnl_bps": 1.0, "oof_total_net_pnl_bps": 31.0, "oof_hit_rate": 0.6},
                "profit_gate": {"passed": True, "best_candidate": {"min_mean_net_pnl_bps": 0.1, "min_total_net_pnl_bps": 3.0}},
            }
        ),
        encoding="utf-8",
    )
    pd.DataFrame(
        {"valid_trades": [10, 12], "valid_mean_net_pnl_bps": [1.1, 0.9], "bootstrap_mean_p05_bps": [0.1, 0.2]}
    ).to_csv(run / "fold_metrics.csv", index=False)
    out = summarize_completed_long_runs([run])
    assert len(out) == 1
    assert bool(out.iloc[0]["v06_long_window_pass"])

from lob_microprice_lab.ensemble import filter_stationary_feature_columns


def test_stationary_feature_filter_drops_absolute_prices() -> None:
    cols = ["mid", "best_bid", "microprice_l3", "microprice_dev_bps_l3", "mid_ret_20r_bps", "imbalance_l1"]
    assert filter_stationary_feature_columns(cols) == ["microprice_dev_bps_l3", "mid_ret_20r_bps", "imbalance_l1"]

from lob_microprice_lab.models import select_feature_columns


def test_feature_selector_drops_future_execution_columns() -> None:
    frame = pd.DataFrame({
        "imbalance_l1": [0.1, 0.2],
        "future_best_bid": [100.0, 101.0],
        "future_best_ask": [100.1, 101.1],
        "future_return_bps": [1.0, -1.0],
        "label": [1, -1],
    })
    assert select_feature_columns(frame) == ["imbalance_l1"]
