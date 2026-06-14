from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v174_long_rescue_state_audit.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v174_long_rescue_state_audit", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v174_marks_v171_window_long_rescue_trades() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        {
            "timestamp": ["2024-01-01T00:00:00Z", "2024-01-01T00:05:00Z"],
            "source": ["a", "b"],
            "side": ["long", "long"],
            "leg": ["rescue", "rescue"],
            "v162_account_return_pct": [-5.0, 3.0],
        }
    )
    window = pd.DataFrame(
        {
            "timestamp": ["2024-01-01T00:00:00Z"],
            "source": ["a"],
            "side": ["long"],
            "leg": ["rescue"],
        }
    )

    out = module._mark_v171_window_members(trades, window)

    assert list(out["v174_in_v171_drawdown_window"]) == [True, False]


def test_v174_feature_delta_compares_drawdown_and_other_long_rescue() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        {
            "v174_rescue_group": ["v171_drawdown_long_rescue", "other_long_rescue", "other_long_rescue"],
            "v162_account_return_pct": [-10.0, 5.0, 7.0],
            "direction_probability": [0.60, 0.70, 0.80],
            "trend_abs_120_bps": [500.0, 100.0, 300.0],
        }
    )

    profile = module._feature_delta_table(frame, ["direction_probability", "trend_abs_120_bps"])

    prob = profile.loc[profile["feature"].eq("direction_probability")].iloc[0]
    assert prob["drawdown_mean"] == 0.60
    assert prob["other_mean"] == 0.75
    assert round(prob["drawdown_minus_other"], 6) == -0.15


def test_v174_payload_declares_audit_only_behavior() -> None:
    module = _load_module()
    group_summary = pd.DataFrame(
        {
            "v174_rescue_group": ["v171_drawdown_long_rescue", "other_long_rescue"],
            "trade_count": [3, 73],
            "account_return_pct": [-21.0, 915.0],
            "win_rate_pct": [0.0, 72.0],
        }
    )
    feature_deltas = pd.DataFrame(
        {
            "feature": ["trend_abs_120_bps"],
            "drawdown_minus_other": [200.0],
        }
    )

    payload = module._payload_for_audit(group_summary, feature_deltas)

    assert payload["config"]["adds_new_trades"] is False
    assert payload["config"]["changes_existing_threshold"] is False
    assert payload["config"]["changes_trade_side"] is False
    assert payload["config"]["promotes_live_trading"] is False
    assert payload["decision"]["drawdown_long_rescue_trade_count"] == 3
    assert payload["decision"]["top_state_difference_feature"] == "trend_abs_120_bps"
