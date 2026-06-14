import numpy as np
import pandas as pd

from lob_microprice_lab.kline_guard import KlineGuardSpec, _guard_values, _slim_backtest_frame


def test_kline_guard_directional_values_for_unsigned_risk_feature():
    frame = pd.DataFrame(
        {
            "signal": [1, -1, 0],
            "kline_15s_rv_6_bps": [2.5, 3.0, 4.0],
        }
    )
    spec = KlineGuardSpec(kline_col="kline_15s_rv_6_bps", directional=True)
    values = _guard_values(frame, spec)
    assert np.allclose(values, [2.5, -3.0, 0.0])


def test_kline_guard_non_directional_values_are_raw_feature_values():
    frame = pd.DataFrame(
        {
            "signal": [1, -1],
            "kline_15s_rv_6_bps": [2.5, 3.0],
        }
    )
    spec = KlineGuardSpec(kline_col="kline_15s_rv_6_bps", directional=False)
    values = _guard_values(frame, spec)
    assert np.allclose(values, [2.5, 3.0])


def test_slim_backtest_frame_keeps_only_repricing_columns():
    frame = pd.DataFrame(
        {
            "fold": [1],
            "timestamp": ["2026-01-01T00:00:00Z"],
            "best_bid": [100.0],
            "best_ask": [100.1],
            "signal": [1],
            "kline_1s_ret_1_bps": [42.0],
            "large_unused_column": ["drop-me"],
        }
    )
    slim = _slim_backtest_frame(frame)
    assert list(slim.columns) == ["fold", "timestamp", "best_bid", "best_ask", "signal"]
    assert slim.loc[0, "signal"] == 1
