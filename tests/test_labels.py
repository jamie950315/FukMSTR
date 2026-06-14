from __future__ import annotations

import pandas as pd

from lob_microprice_lab.config import FeatureConfig
from lob_microprice_lab.features import build_features
from lob_microprice_lab.labels import add_future_labels
from lob_microprice_lab.sample_data import generate_sample_data


def test_add_future_labels(tmp_path):
    book_path, trades_path = generate_sample_data(tmp_path, rows=300, depth=3, seed=2)
    book = pd.read_csv(book_path)
    trades = pd.read_csv(trades_path)
    features = build_features(book, trades, FeatureConfig(depth_levels=[1, 3], trade_windows_sec=[1.0]))
    labeled = add_future_labels(features, horizon_sec=1.0, threshold_bps=0.5)

    assert len(labeled) < len(features)
    assert set(labeled["label"].unique()).issubset({-1, 0, 1})
    assert labeled["future_return_bps"].notna().all()
