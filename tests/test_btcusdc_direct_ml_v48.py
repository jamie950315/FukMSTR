from __future__ import annotations

import pandas as pd

from lob_microprice_lab.btcusdc_direct_ml import (
    build_direct_ml_features,
    run_prequential_gate_selection,
)


def test_build_direct_ml_features_accepts_one_bar_lookback() -> None:
    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=6, freq="min", tz="UTC"),
            "open": [100, 101, 102, 103, 104, 105],
            "high": [101, 102, 103, 104, 105, 106],
            "low": [99, 100, 101, 102, 103, 104],
            "close": [100, 101, 102, 103, 104, 105],
            "volume": [10, 11, 12, 13, 14, 15],
            "taker_buy_base_volume": [6, 5, 7, 6, 8, 7],
        }
    )

    features, feature_cols = build_direct_ml_features(bars, lookbacks=[1, 3])

    assert "ret_1" in feature_cols
    assert "vol_ratio_1" in feature_cols
    assert len(features) == len(bars)
    assert features["ret_1"].notna().sum() == 5


def test_prequential_gate_selection_uses_only_prior_folds() -> None:
    candidates = pd.DataFrame(
        [
            {"config": "a", "fold": 1, "active": True, "validation_total": 100.0, "validation_trades": 10},
            {"config": "b", "fold": 1, "active": True, "validation_total": 10.0, "validation_trades": 10},
            {"config": "a", "fold": 2, "active": True, "validation_total": -50.0, "validation_trades": 10},
            {"config": "b", "fold": 2, "active": True, "validation_total": 500.0, "validation_trades": 10},
            {"config": "a", "fold": 3, "active": True, "validation_total": 1.0, "validation_trades": 10},
            {"config": "b", "fold": 3, "active": True, "validation_total": 999.0, "validation_trades": 10},
        ]
    )

    selected, summary = run_prequential_gate_selection(candidates, warmup_folds=1)

    fold2 = selected.loc[selected["fold"].astype(int) == 2].iloc[0]
    fold3 = selected.loc[selected["fold"].astype(int) == 3].iloc[0]
    assert fold2["config"] == "a"
    assert float(fold2["validation_total"]) == -50.0
    assert fold3["config"] == "b"
    assert float(summary["total"]) == 949.0
