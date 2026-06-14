from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v183_short_base_momentum_stepup.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v183_short_base_momentum_stepup", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v183_steps_up_only_existing_v182_momentum_boost_rows() -> None:
    module = _load_module()
    policy = module.ShortBaseMomentumStepupPolicy(
        policy="example",
        stepup_multiplier=1.25,
    )
    trades = pd.DataFrame(
        {
            "v182_state_action": ["short_base_momentum_boost", "unchanged", "long_base_funding_boost"],
            "v182_account_return_pct": [10.0, 20.0, 30.0],
            "v182_account_pnl_bps": [100.0, 200.0, 300.0],
        }
    )

    out = module._apply_short_base_momentum_stepup_policy(trades, policy)

    assert list(out["v183_state_multiplier"]) == [1.25, 1.0, 1.0]
    assert list(out["v183_state_action"]) == ["short_base_momentum_stepup", "unchanged", "unchanged"]
    assert list(out["v183_account_return_pct"]) == [12.5, 20.0, 30.0]
    assert list(out["v183_account_pnl_bps"]) == [125.0, 200.0, 300.0]


def test_v183_comparison_requires_holdout_and_stepup_diversity() -> None:
    module = _load_module()
    timestamps = pd.date_range("2024-01-01T00:00:00Z", periods=40, freq="MS")
    baseline = pd.DataFrame(
        {
            "timestamp": timestamps,
            "v183_policy": ["v182_baseline_no_short_base_momentum_stepup"] * len(timestamps),
            "v183_account_return_pct": [10.0] * len(timestamps),
            "v183_account_pnl_bps": [1000.0] * len(timestamps),
            "v183_state_action": ["unchanged"] * len(timestamps),
            "v183_state_multiplier": [1.0] * len(timestamps),
        }
    )
    candidate = baseline.copy()
    candidate["v183_policy"] = "candidate"
    candidate["v183_account_return_pct"] = [11.0] * len(timestamps)
    candidate["v183_account_pnl_bps"] = [1100.0] * len(timestamps)
    candidate["v183_state_action"] = ["short_base_momentum_stepup"] * len(timestamps)
    candidate["v183_state_multiplier"] = [1.25] * len(timestamps)

    comparison = module._compare_policies(
        {"v182_baseline_no_short_base_momentum_stepup": baseline, "candidate": candidate},
        module._baseline_months(baseline),
    )

    row = comparison.loc[comparison["policy"].eq("candidate")].iloc[0]
    assert row["momentum_stepup_passed"] is True
    assert row["stepup_trade_count"] == 40
    assert row["stepup_active_month_count"] == 40
    assert row["stepup_max_month_trade_share_pct"] == 2.5
    assert row["holdout_return_delta_pct"] > 0.0


def test_v183_payload_keeps_candidate_research_only() -> None:
    module = _load_module()
    comparison = pd.DataFrame(
        {
            "policy": ["v182_baseline_no_short_base_momentum_stepup", "candidate"],
            "momentum_stepup_passed": [False, True],
            "total_account_return_pct": [100.0, 110.0],
            "return_delta_pct": [0.0, 10.0],
            "max_drawdown_pct": [-10.0, -9.0],
            "drawdown_improvement_pct": [0.0, 1.0],
            "holdout_return_delta_pct": [0.0, 5.5],
            "holdout_drawdown_improvement_pct": [0.0, 1.0],
            "stepup_trade_count": [0, 44],
            "stepup_active_month_count": [0, 16],
            "stepup_max_month_trade_share_pct": [0.0, 14.0],
        }
    )

    payload = module._payload_for_comparison(comparison, selected_policy="candidate")

    assert payload["decision"]["status"] == "short_base_momentum_stepup_candidate_ready"
    assert payload["decision"]["promote_to_live"] is False
    assert payload["config"]["adds_new_trades"] is False
    assert payload["config"]["changes_trade_side"] is False
    assert payload["config"]["changes_existing_threshold"] is False


def test_v183_baseline_policy_does_not_mark_stepup_actions() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        {
            "v182_state_action": ["short_base_momentum_boost"],
            "v182_account_return_pct": [10.0],
            "v182_account_pnl_bps": [1000.0],
        }
    )

    out = module._apply_short_base_momentum_stepup_policy(trades, module.POLICIES[0])

    assert out.iloc[0]["v183_state_action"] == "unchanged"
    assert out.iloc[0]["v183_state_multiplier"] == 1.0
