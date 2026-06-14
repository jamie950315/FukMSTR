from __future__ import annotations

from lob_microprice_lab.config import FeatureConfig
from lob_microprice_lab.features import build_features
from lob_microprice_lab.sample_data import generate_sample_data


def test_build_features_from_sample(tmp_path):
    book_path, trades_path = generate_sample_data(tmp_path, rows=300, depth=5, seed=1)
    import pandas as pd

    book = pd.read_csv(book_path)
    trades = pd.read_csv(trades_path)
    features = build_features(book, trades, FeatureConfig(depth_levels=[1, 3, 5], trade_windows_sec=[1.0, 5.0]))

    assert len(features) > 250
    assert "mid" in features.columns
    assert "microprice_dev_bps" in features.columns
    assert "imbalance_l3" in features.columns
    assert "trade_imbalance_1s" in features.columns
    assert features["spread_bps"].min() > 0
