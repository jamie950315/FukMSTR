from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v170_execution_aware_risk_control.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v170_execution_aware_risk_control", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v170_policy_scales_existing_trades_without_changing_side_or_leg() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        {
            "month": ["2024-07", "2024-08", "2024-09"],
            "side": ["long", "short", "long"],
            "leg": ["base", "rescue", "base"],
            "v162_account_return_pct": [10.0, -4.0, 6.0],
            "v162_account_pnl_bps": [1000.0, -400.0, 600.0],
        }
    )
    gate = pd.DataFrame(
        {
            "month": ["2024-07", "2024-08", "2024-09"],
            "execution_readiness_mode": ["maker_only_required", "maker_priority_required", "taker_allowed"],
            "live_gate_action": ["block_taker_execution", "prefer_maker_or_skip", "normal_cost_monitoring"],
        }
    )
    policy = module.ExecutionRiskPolicy(
        policy="skip_maker_only_half_priority",
        maker_only_multiplier=0.0,
        maker_priority_multiplier=0.5,
        no_trade_multiplier=0.0,
    )

    out = module._apply_execution_risk_policy(trades, gate, policy)

    assert list(out["side"]) == ["long", "short", "long"]
    assert list(out["leg"]) == ["base", "rescue", "base"]
    assert list(out["v170_execution_multiplier"]) == [0.0, 0.5, 1.0]
    assert list(out["v170_account_return_pct"]) == [0.0, -2.0, 6.0]
    assert list(out["v170_executed_trade"]) == [False, True, True]


def test_v170_metrics_track_executed_count_drawdown_and_month_stability() -> None:
    module = _load_module()
    path = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2024-07-01T00:00:00Z",
                    "2024-07-02T00:00:00Z",
                    "2024-08-01T00:00:00Z",
                ],
                utc=True,
            ),
            "v170_account_return_pct": [10.0, -12.0, 6.0],
            "v170_account_pnl_bps": [1000.0, -1200.0, 600.0],
            "v170_executed_trade": [True, True, False],
        }
    )
    baseline_months = pd.Index(["2024-07", "2024-08"], name="month")

    metrics = module._policy_metrics("sample", path, baseline_months=baseline_months)

    assert metrics["policy"] == "sample"
    assert metrics["trade_count"] == 3
    assert metrics["executed_trade_count"] == 2
    assert metrics["total_account_return_pct"] == 4.0
    assert metrics["max_drawdown_pct"] == -12.0
    assert metrics["positive_months"] == 1
    assert metrics["month_count"] == 2
    assert metrics["win_rate_pct"] == 50.0


def test_v170_payload_declares_risk_control_only_behavior() -> None:
    module = _load_module()
    comparison = pd.DataFrame(
        {
            "policy": ["baseline", "candidate"],
            "total_account_return_pct": [100.0, 95.0],
            "max_drawdown_pct": [-20.0, -10.0],
            "positive_months": [20, 21],
            "month_count": [24, 24],
            "executed_trade_count": [100, 80],
        }
    )

    payload = module._payload_for_comparison(comparison, selected_policy="candidate")

    assert payload["config"]["adds_new_trades"] is False
    assert payload["config"]["changes_existing_threshold"] is False
    assert payload["config"]["changes_trade_side"] is False
    assert payload["config"]["promotes_live_trading"] is False
    assert payload["decision"]["selected_policy"] == "candidate"
    assert payload["decision"]["selected_return_delta_pct"] == -5.0
    assert payload["decision"]["selected_drawdown_improvement_pct"] == 10.0
