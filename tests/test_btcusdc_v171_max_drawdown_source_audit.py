from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v171_max_drawdown_source_audit.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v171_max_drawdown_source_audit", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v171_finds_peak_to_trough_max_drawdown_window() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        {
            "timestamp": [
                "2024-01-01T00:00:00Z",
                "2024-01-02T00:00:00Z",
                "2024-01-03T00:00:00Z",
                "2024-01-04T00:00:00Z",
            ],
            "v162_account_return_pct": [10.0, -3.0, -4.0, 2.0],
            "v162_account_pnl_bps": [1000.0, -300.0, -400.0, 200.0],
            "side": ["long", "long", "short", "short"],
            "leg": ["base", "base", "base", "rescue"],
            "source": ["a", "a", "b", "b"],
        }
    )

    annotated = module._annotate_drawdown_path(trades)
    window, summary = module._max_drawdown_window(annotated)

    assert summary["max_drawdown_pct"] == -7.0
    assert summary["peak_timestamp"] == "2024-01-01 00:00:00+00:00"
    assert summary["trough_timestamp"] == "2024-01-03 00:00:00+00:00"
    assert summary["window_trade_count"] == 2
    assert list(window["v162_account_return_pct"]) == [-3.0, -4.0]


def test_v171_attributes_drawdown_window_by_group() -> None:
    module = _load_module()
    window = pd.DataFrame(
        {
            "side": ["long", "short", "short"],
            "leg": ["base", "base", "rescue"],
            "source": ["a", "b", "b"],
            "v162_account_return_pct": [-2.0, -4.0, 1.0],
            "v162_account_pnl_bps": [-200.0, -400.0, 100.0],
            "account_leverage": [2.0, 3.0, 1.0],
            "position_weight": [1.0, 0.5, 2.0],
            "direction_probability": [0.61, 0.62, 0.70],
        }
    )

    out = module._attribute_window(window, ["side"])

    short = out.loc[out["side"].eq("short")].iloc[0]
    assert short["trade_count"] == 2
    assert short["account_return_pct"] == -3.0
    assert short["loss_trade_count"] == 1
    assert short["avg_account_leverage"] == 2.0


def test_v171_payload_declares_audit_only_behavior() -> None:
    module = _load_module()
    summary = {
        "max_drawdown_pct": -7.0,
        "window_trade_count": 2,
        "peak_timestamp": "2024-01-01 00:00:00+00:00",
        "trough_timestamp": "2024-01-03 00:00:00+00:00",
    }
    attribution = pd.DataFrame(
        {
            "side": ["long", "short"],
            "trade_count": [1, 1],
            "account_return_pct": [-3.0, -4.0],
        }
    )

    payload = module._payload_for_audit(summary, attribution)

    assert payload["config"]["adds_new_trades"] is False
    assert payload["config"]["changes_existing_threshold"] is False
    assert payload["config"]["changes_trade_side"] is False
    assert payload["config"]["promotes_live_trading"] is False
    assert payload["decision"]["max_drawdown_pct"] == -7.0
    assert payload["decision"]["dominant_loss_group"] == "short"
