from __future__ import annotations

import pandas as pd

from lob_microprice_lab.kline_features import build_kline_feature_frame, build_mid_candles_from_book, parse_timeframe_seconds


def test_parse_timeframe_seconds() -> None:
    assert parse_timeframe_seconds("500ms") == 0.5
    assert parse_timeframe_seconds("5s") == 5.0
    assert parse_timeframe_seconds("2m") == 120.0


def test_kline_alignment_uses_only_closed_bars() -> None:
    ts = pd.date_range("2024-01-01T00:00:00Z", periods=12, freq="1s")
    book = pd.DataFrame({"timestamp": ts, "best_bid": range(100, 112), "best_ask": range(101, 113)})
    events = pd.DataFrame({"timestamp": ts})
    candles = build_mid_candles_from_book(book, timeframe="3s")
    assert set(["timestamp", "close_ts", "open", "high", "low", "close", "volume"]).issubset(candles.columns)

    result = build_kline_feature_frame(events, book=book, timeframes=["3s"], decision_lag_sec=0.0, lookbacks=[1, 2])
    assert result.audit["ok"] is True
    assert result.audit["max_overrun_ns"] == 0
    assert "kline_3s_signal" in result.features.columns
    # The event at exactly 00:00:03 can use the candle closed at 00:00:03, so age is zero.
    assert float(result.features.loc[3, "kline_3s_age_sec"]) == 0.0
    # The earlier in-bar events have no closed candle yet and are filled with zeros.
    assert float(result.features.loc[1, "kline_3s_age_sec"]) == 0.0
