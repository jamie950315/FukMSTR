from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v169_fragile_execution_profile.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v169_fragile_execution_profile", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v169_attaches_monthly_execution_mode_to_each_trade() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        {
            "month": ["2024-07", "2024-08"],
            "v162_account_return_pct": [1.0, -0.5],
            "side": ["long", "short"],
            "leg": ["base", "rescue"],
        }
    )
    gate = pd.DataFrame(
        {
            "month": ["2024-07", "2024-08"],
            "execution_readiness_mode": ["maker_only_required", "taker_allowed"],
            "live_gate_action": ["block_taker_execution", "normal_cost_monitoring"],
        }
    )

    out = module._attach_execution_mode(trades, gate)

    assert list(out["execution_readiness_mode"]) == ["maker_only_required", "taker_allowed"]
    assert list(out["fragile_execution_group"]) == ["fragile_execution", "normal_execution"]


def test_v169_profiles_return_win_rate_and_structure_by_group() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        {
            "fragile_execution_group": ["fragile_execution", "fragile_execution", "normal_execution"],
            "execution_readiness_mode": ["maker_only_required", "maker_priority_required", "taker_allowed"],
            "v162_account_return_pct": [1.0, -0.5, 2.0],
            "v162_account_pnl_bps": [100.0, -50.0, 200.0],
            "side": ["long", "short", "long"],
            "leg": ["base", "base", "rescue"],
            "account_leverage": [3.0, 2.0, 1.0],
            "position_weight": [1.0, 0.5, 1.0],
            "direction_probability": [0.62, 0.61, 0.7],
        }
    )

    profile = module._group_profile(trades, ["fragile_execution_group"])

    fragile = profile.loc[profile["fragile_execution_group"].eq("fragile_execution")].iloc[0]
    assert fragile["trade_count"] == 2
    assert fragile["account_return_pct"] == 0.5
    assert fragile["win_rate_pct"] == 50.0
    assert fragile["long_trade_count"] == 1
    assert fragile["base_trade_count"] == 2


def test_v169_payload_declares_audit_only_behavior() -> None:
    module = _load_module()
    profile = pd.DataFrame(
        {
            "fragile_execution_group": ["fragile_execution", "normal_execution"],
            "trade_count": [2, 3],
            "account_return_pct": [0.5, 2.0],
            "win_rate_pct": [50.0, 66.6667],
        }
    )

    payload = module._payload_for_profiles(profile)

    assert payload["config"]["adds_new_trades"] is False
    assert payload["config"]["changes_existing_threshold"] is False
    assert payload["config"]["promotes_live_trading"] is False
    assert payload["decision"]["fragile_trade_count"] == 2
