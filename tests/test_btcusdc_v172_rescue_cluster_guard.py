from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v172_rescue_cluster_guard.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v172_rescue_cluster_guard", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v172_counts_only_prior_same_side_rescue_trades_inside_lookback() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        {
            "timestamp": [
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:10:00Z",
                "2024-01-01T01:00:00Z",
                "2024-01-01T01:10:00Z",
                "2024-01-01T03:10:00Z",
            ],
            "side": ["long", "long", "long", "short", "long"],
            "leg": ["rescue", "base", "rescue", "rescue", "rescue"],
            "v162_account_return_pct": [1.0, 2.0, 3.0, 4.0, 5.0],
            "v162_account_pnl_bps": [100.0, 200.0, 300.0, 400.0, 500.0],
        }
    )

    out = module._annotate_rescue_cluster_context(trades, lookback_minutes=120)

    assert list(out["v172_prior_same_side_rescue_count"]) == [0, 1, 1, 0, 0]


def test_v172_guard_scales_only_rescue_trades_after_trigger() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2024-01-01T00:00:00Z", "2024-01-01T00:10:00Z", "2024-01-01T00:20:00Z"],
                utc=True,
            ),
            "side": ["long", "long", "long"],
            "leg": ["rescue", "base", "rescue"],
            "v162_account_return_pct": [10.0, -4.0, -8.0],
            "v162_account_pnl_bps": [1000.0, -400.0, -800.0],
            "v172_prior_same_side_rescue_count": [0, 1, 1],
        }
    )
    policy = module.RescueClusterPolicy(
        policy="half_after_1",
        lookback_minutes=120,
        trigger_prior_rescue_count=1,
        rescue_multiplier=0.5,
    )

    out = module._apply_rescue_cluster_guard(trades, policy)

    assert list(out["v172_guard_applied"]) == [False, False, True]
    assert list(out["v172_rescue_cluster_multiplier"]) == [1.0, 1.0, 0.5]
    assert list(out["v172_account_return_pct"]) == [10.0, -4.0, -4.0]
    assert list(out["side"]) == ["long", "long", "long"]


def test_v172_payload_declares_guard_only_behavior() -> None:
    module = _load_module()
    comparison = pd.DataFrame(
        {
            "policy": ["v162_baseline_no_cluster_guard", "candidate"],
            "total_account_return_pct": [100.0, 98.0],
            "max_drawdown_pct": [-20.0, -15.0],
            "worst_month_pct": [-5.0, -4.0],
            "guarded_trade_count": [0, 2],
        }
    )

    payload = module._payload_for_comparison(comparison, selected_policy="candidate")

    assert payload["config"]["adds_new_trades"] is False
    assert payload["config"]["changes_existing_threshold"] is False
    assert payload["config"]["changes_trade_side"] is False
    assert payload["config"]["promotes_live_trading"] is False
    assert payload["decision"]["selected_policy"] == "candidate"
    assert payload["decision"]["selected_return_delta_pct"] == -2.0
    assert payload["decision"]["selected_drawdown_improvement_pct"] == 5.0
