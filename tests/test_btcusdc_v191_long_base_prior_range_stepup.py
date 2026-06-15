from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v191_long_base_prior_range_stepup.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v191_long_base_prior_range_stepup", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v191_steps_up_only_unchanged_long_base_prior_range_rows() -> None:
    module = _load_module()
    policy = module.LongBasePriorRangeStepupPolicy(
        policy="example",
        min_prior_range_pos_1440=0.326,
        stepup_multiplier=1.25,
    )
    trades = pd.DataFrame(
        {
            "side": ["long", "long", "short", "long", "long", "long"],
            "leg": ["base", "base", "base", "rescue", "base", "base"],
            "v188_state_action": [
                "unchanged",
                "unchanged",
                "unchanged",
                "unchanged",
                "drought_trend_emotion_stepup",
                "unchanged",
            ],
            "v189_state_action": [
                "unchanged",
                "unchanged",
                "unchanged",
                "unchanged",
                "unchanged",
                "rescue_mid_range_extreme_stepup",
            ],
            "v190_state_action": [
                "unchanged",
                "unchanged",
                "unchanged",
                "unchanged",
                "unchanged",
                "unchanged",
            ],
            "prior_range_pos_1440": [0.40, 0.20, 0.50, 0.60, 0.70, 0.80],
            "v190_account_return_pct": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
            "v190_account_pnl_bps": [100.0, 200.0, 300.0, 400.0, 500.0, 600.0],
        }
    )

    out = module._apply_long_base_prior_range_stepup_policy(trades, policy)

    assert list(out["v191_state_multiplier"]) == [1.25, 1.0, 1.0, 1.0, 1.0, 1.0]
    assert list(out["v191_state_action"]) == [
        "long_base_prior_range_stepup",
        "unchanged",
        "unchanged",
        "unchanged",
        "unchanged",
        "unchanged",
    ]
    assert list(out["v191_account_return_pct"]) == [12.5, 20.0, 30.0, 40.0, 50.0, 60.0]
    assert list(out["v191_account_pnl_bps"]) == [125.0, 200.0, 300.0, 400.0, 500.0, 600.0]


def test_v191_comparison_requires_holdout_and_concentration_gates() -> None:
    module = _load_module()
    timestamps = pd.date_range("2024-01-01T00:00:00Z", periods=40, freq="MS")
    baseline = pd.DataFrame(
        {
            "timestamp": timestamps,
            "v191_policy": ["v190_baseline_no_long_base_prior_range_stepup"] * len(timestamps),
            "v191_account_return_pct": [10.0] * len(timestamps),
            "v191_account_pnl_bps": [1000.0] * len(timestamps),
            "v191_state_action": ["unchanged"] * len(timestamps),
            "v191_state_multiplier": [1.0] * len(timestamps),
        }
    )
    candidate = baseline.copy()
    candidate["v191_policy"] = "candidate"
    candidate["v191_account_return_pct"] = [11.0] * len(timestamps)
    candidate["v191_account_pnl_bps"] = [1100.0] * len(timestamps)
    candidate["v191_state_action"] = ["long_base_prior_range_stepup"] * len(timestamps)
    candidate["v191_state_multiplier"] = [1.25] * len(timestamps)

    comparison = module._compare_policies(
        {"v190_baseline_no_long_base_prior_range_stepup": baseline, "candidate": candidate},
        module._baseline_months(baseline),
    )

    row = comparison.loc[comparison["policy"].eq("candidate")].iloc[0]
    assert row["prior_range_stepup_passed"] is True
    assert row["stepup_trade_count"] == 40
    assert row["stepup_active_month_count"] == 40
    assert row["stepup_max_month_trade_share_pct"] == 2.5
    assert row["holdout_return_delta_pct"] > 0.0


def test_v191_payload_includes_v190_v191_iteration_metrics() -> None:
    module = _load_module()
    comparison = pd.DataFrame(
        {
            "policy": ["v190_baseline_no_long_base_prior_range_stepup", "candidate"],
            "prior_range_stepup_passed": [False, True],
            "total_account_return_pct": [100.0, 140.0],
            "return_delta_pct": [0.0, 40.0],
            "return_improvement_rate": [0.0, 0.4],
            "max_drawdown_pct": [-10.0, -10.0],
            "drawdown_improvement_pct": [0.0, 0.0],
            "positive_months": [24, 24],
            "month_count": [24, 24],
            "holdout_return_pct": [30.0, 50.0],
            "holdout_return_delta_pct": [0.0, 20.0],
            "holdout_max_drawdown_pct": [-5.0, -5.0],
            "holdout_drawdown_improvement_pct": [0.0, 0.0],
            "holdout_positive_months": [6, 6],
            "holdout_month_count": [6, 6],
            "stepup_trade_count": [0, 105],
            "stepup_active_month_count": [0, 23],
            "stepup_max_month_trade_share_pct": [0.0, 17.14],
            "stepup_max_single_trade_delta_share_pct": [0.0, 15.97],
        }
    )

    payload = module._payload_for_comparison(comparison, selected_policy="candidate")

    table = payload["iteration_metrics_table"]
    assert table[0]["version"] == "V190"
    assert table[1]["version"] == "V191"
    assert table[1]["account_return_pct"] == 140.0
    assert table[1]["improvement_pct"] == 40.0
    assert table[1]["positive_months"] == "24/24"
    assert table[1]["holdout_months"] == "6/6"
    assert payload["decision"]["promote_to_live"] is False


def test_v191_baseline_policy_does_not_mark_stepup_actions() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        {
            "side": ["long"],
            "leg": ["base"],
            "v188_state_action": ["unchanged"],
            "v189_state_action": ["unchanged"],
            "v190_state_action": ["unchanged"],
            "prior_range_pos_1440": [999.0],
            "v190_account_return_pct": [10.0],
            "v190_account_pnl_bps": [1000.0],
        }
    )

    out = module._apply_long_base_prior_range_stepup_policy(trades, module.POLICIES[0])

    assert out.iloc[0]["v191_state_action"] == "unchanged"
    assert out.iloc[0]["v191_state_multiplier"] == 1.0
