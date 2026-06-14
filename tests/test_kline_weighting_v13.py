from __future__ import annotations

import numpy as np
import pandas as pd

from lob_microprice_lab.kline_weighting import apply_kline_weights, detect_kline_signal_columns, generate_weight_candidates


def test_apply_kline_weights_replaces_probability_edge() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=4, freq="1s", tz="UTC"),
            "best_bid": [100.0, 101.0, 102.0, 103.0],
            "best_ask": [100.1, 101.1, 102.1, 103.1],
            "prob_up": [0.6, 0.4, 0.6, 0.4],
            "prob_down": [0.4, 0.6, 0.4, 0.6],
            "label": [1, -1, 1, -1],
            "kline_1s_signal": [0.5, -0.5, 0.25, -0.25],
        }
    )
    out = apply_kline_weights(frame, weights={"base": 0.5, "kline_1s_signal": 0.5})
    expected = 0.5 * np.array([0.2, -0.2, 0.2, -0.2]) + 0.5 * np.array([0.5, -0.5, 0.25, -0.25])
    assert np.allclose(out["prob_edge"], expected)
    assert np.allclose(out["prob_up"] - out["prob_down"], expected)
    assert out["pred_label"].tolist() == [1, -1, 1, -1]


def test_generate_weight_candidates_includes_base_and_timeframe_profiles() -> None:
    cols = ["kline_1s_signal", "kline_5s_signal"]
    candidates = generate_weight_candidates(cols, base_weight_values=[0.0, 0.5, 1.0], kline_signs=[-1, 1])
    assert {"base": 1.0} in candidates
    assert any("kline_1s_signal" in c and c.get("base") == 0.5 for c in candidates)
    assert detect_kline_signal_columns(pd.DataFrame(columns=cols)) == cols
