from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PINE_PATH = ROOT / "tradingview" / "btcusdc_v193_companion_strategy.pine"
DOC_PATH = ROOT / "docs" / "TRADINGVIEW_V193_COMPANION.md"


def test_tradingview_v193_companion_pine_contains_required_strategy_surface() -> None:
    source = PINE_PATH.read_text(encoding="utf-8")

    assert source.startswith("//@version=6")
    assert "strategy(" in source
    assert "BTCUSDC V193 Companion" in source
    assert "V193_PREMIUM_THRESHOLD_BPS = -4.576517" in source
    assert "request.security(" in source
    assert "barmerge.lookahead_off" in source
    assert "strategy.entry(" in source
    assert "strategy.exit(" in source
    assert "alertcondition(" in source
    assert "tradingview_v193_companion" in source
    assert "v193ThrottleBlock" in source
    assert "This script is a TradingView companion, not a byte-for-byte port" in source
    assert "lookahead_on" not in source


def test_tradingview_v193_companion_docs_explain_limits_and_usage() -> None:
    docs = DOC_PATH.read_text(encoding="utf-8")

    assert "TradingView V193 Companion Strategy" in docs
    assert "cannot exactly reproduce the backend V193 research path" in docs
    assert "indicator_key" in docs
    assert "v188_state_action" in docs
    assert "premium_close_bps_6h >= -4.576517" in docs
    assert "Paste `tradingview/btcusdc_v193_companion_strategy.pine`" in docs
