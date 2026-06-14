from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v184_long_base_low_premium_throttle.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v184_long_base_low_premium_throttle", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v184_throttles_only_unchanged_long_base_low_premium_rows() -> None:
    module = _load_module()
    policy = module.LongBaseLowPremiumThrottlePolicy(
        policy="example",
        max_premium_z_120d=-1.8,
        throttle_multiplier=0.25,
    )
    trades = pd.DataFrame(
        {
            "side": ["long", "long", "short", "long"],
            "leg": ["base", "base", "base", "rescue"],
            "v183_state_action": ["unchanged", "short_base_momentum_stepup", "unchanged", "unchanged"],
            "premium_z_120d": [-2.0, -2.0, -2.0, -2.0],
            "v183_account_return_pct": [10.0, 20.0, 30.0, 40.0],
            "v183_account_pnl_bps": [100.0, 200.0, 300.0, 400.0],
        }
    )

    out = module._apply_long_base_low_premium_throttle_policy(trades, policy)

    assert list(out["v184_state_multiplier"]) == [0.25, 1.0, 1.0, 1.0]
    assert list(out["v184_state_action"]) == [
        "long_base_low_premium_throttle",
        "unchanged",
        "unchanged",
        "unchanged",
    ]
    assert list(out["v184_account_return_pct"]) == [2.5, 20.0, 30.0, 40.0]
    assert list(out["v184_account_pnl_bps"]) == [25.0, 200.0, 300.0, 400.0]


def test_v184_comparison_requires_holdout_and_throttle_diversity() -> None:
    module = _load_module()
    timestamps = pd.date_range("2024-01-01T00:00:00Z", periods=40, freq="MS")
    baseline = pd.DataFrame(
        {
            "timestamp": timestamps,
            "v184_policy": ["v183_baseline_no_long_base_low_premium_throttle"] * len(timestamps),
            "v184_account_return_pct": [10.0] * len(timestamps),
            "v184_account_pnl_bps": [1000.0] * len(timestamps),
            "v184_state_action": ["unchanged"] * len(timestamps),
            "v184_state_multiplier": [1.0] * len(timestamps),
        }
    )
    candidate = baseline.copy()
    candidate["v184_policy"] = "candidate"
    candidate["v184_account_return_pct"] = [11.0] * len(timestamps)
    candidate["v184_account_pnl_bps"] = [1100.0] * len(timestamps)
    candidate["v184_state_action"] = ["long_base_low_premium_throttle"] * len(timestamps)
    candidate["v184_state_multiplier"] = [0.0] * len(timestamps)

    comparison = module._compare_policies(
        {"v183_baseline_no_long_base_low_premium_throttle": baseline, "candidate": candidate},
        module._baseline_months(baseline),
    )

    row = comparison.loc[comparison["policy"].eq("candidate")].iloc[0]
    assert row["low_premium_throttle_passed"] is True
    assert row["throttled_trade_count"] == 40
    assert row["throttled_active_month_count"] == 40
    assert row["throttled_max_month_trade_share_pct"] == 2.5
    assert row["holdout_return_delta_pct"] > 0.0


def test_v184_payload_keeps_candidate_research_only() -> None:
    module = _load_module()
    comparison = pd.DataFrame(
        {
            "policy": ["v183_baseline_no_long_base_low_premium_throttle", "candidate"],
            "low_premium_throttle_passed": [False, True],
            "total_account_return_pct": [100.0, 110.0],
            "return_delta_pct": [0.0, 10.0],
            "max_drawdown_pct": [-10.0, -9.0],
            "drawdown_improvement_pct": [0.0, 1.0],
            "holdout_return_delta_pct": [0.0, 5.5],
            "holdout_drawdown_improvement_pct": [0.0, 1.0],
            "throttled_trade_count": [0, 27],
            "throttled_active_month_count": [0, 10],
            "throttled_max_month_trade_share_pct": [0.0, 29.0],
            "throttled_max_single_trade_delta_share_pct": [0.0, 28.0],
        }
    )

    payload = module._payload_for_comparison(comparison, selected_policy="candidate")

    assert payload["decision"]["status"] == "long_base_low_premium_throttle_candidate_ready"
    assert payload["decision"]["promote_to_live"] is False
    assert payload["config"]["adds_new_trades"] is False
    assert payload["config"]["changes_trade_side"] is False
    assert payload["config"]["changes_existing_threshold"] is False


def test_v184_baseline_policy_does_not_mark_throttle_actions() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        {
            "side": ["long"],
            "leg": ["base"],
            "v183_state_action": ["unchanged"],
            "premium_z_120d": [-9.0],
            "v183_account_return_pct": [10.0],
            "v183_account_pnl_bps": [1000.0],
        }
    )

    out = module._apply_long_base_low_premium_throttle_policy(trades, module.POLICIES[0])

    assert out.iloc[0]["v184_state_action"] == "unchanged"
    assert out.iloc[0]["v184_state_multiplier"] == 1.0
