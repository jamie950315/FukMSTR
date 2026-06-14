
from __future__ import annotations

import numpy as np
import pandas as pd

from lob_microprice_lab.kline_guard import KlineGuardSpec
from lob_microprice_lab.profit_lock import ProfitLockGate, assert_sparse_matches_dense, run_profit_lock_certificate
from lob_microprice_lab.profit_stability import _prepare_execution_arrays


def test_sparse_shift_metrics_match_dense_evaluator() -> None:
    n = 64
    ts = pd.date_range("2026-01-01", periods=n, freq="500ms")
    px = 10000.0 + np.sin(np.arange(n) / 5.0) * 3.0 + np.arange(n) * 0.1
    frame = pd.DataFrame(
        {
            "timestamp": ts,
            "best_bid": px - 0.5,
            "best_ask": px + 0.5,
        }
    )
    raw = np.zeros(n, dtype=int)
    raw[[2, 5, 9, 14, 21, 27, 33, 41, 49, 57]] = [1, -1, 1, -1, 1, 1, -1, 1, -1, 1]
    arrays = _prepare_execution_arrays(frame, horizon_sec=4.0, latency_sec=0.5)
    assert_sparse_matches_dense(raw, arrays, cost_bps=1.5, shifts=[0, 1, 3, 11, 29, 47])


def test_profit_lock_certificate_smoke() -> None:
    result = run_profit_lock_certificate(
        base_ensemble_dir="runs/research_v09_ensemble_h90_5fold_stationary",
        kline_ensemble_dir="runs/research_v13_kline_h90_5fold_stationary_v12folds",
        out_dir="runs/test_v16_profit_lock_certificate",
        horizon_sec=90,
        cost_bps=1.5,
        latency_sec=0.5,
        selected_spec=KlineGuardSpec(
            edge_threshold=0.1,
            kline_alpha=0.125,
            ofi_col="ofi_sum_l5_norm",
            ofi_quantile=0.9,
            kline_col="kline_15s_rv_6_bps",
            kline_quantile=0.0,
            kline_operator=">=",
            directional=True,
        ),
        shift_null_runs=20,
        gate=ProfitLockGate(max_addone_family_p=0.05),
        clean=True,
    )
    aggregate = result["aggregate"]
    assert aggregate["trades"] == 20
    assert aggregate["total_net_pnl_bps"] > 180.0
    assert aggregate["configured_top_winner_removed_total_bps"] > 0.0
    assert aggregate["gate"]["passed"] is True
