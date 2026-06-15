from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v194_long_rescue_premium_discount_stepup.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v194_long_rescue_premium_discount_stepup", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v194_steps_only_unchanged_long_rescue_premium_discount_rows() -> None:
    module = _load_module()
    policy = module.LongRescuePremiumDiscountStepupPolicy(
        policy="example",
        max_premium_open=-0.000351,
        stepup_multiplier=1.25,
    )
    trades = pd.DataFrame(
        {
            "side": ["long", "long", "short", "long", "long", "long"],
            "leg": ["rescue", "rescue", "rescue", "base", "rescue", "rescue"],
            "v188_state_action": ["unchanged"] * 6,
            "v189_state_action": ["unchanged"] * 6,
            "v190_state_action": ["unchanged"] * 6,
            "v191_state_action": ["unchanged"] * 6,
            "v192_state_action": ["unchanged"] * 6,
            "v193_state_action": [
                "unchanged",
                "unchanged",
                "unchanged",
                "unchanged",
                "unchanged",
                "long_base_top5_premium6h_throttle",
            ],
            "premium_open": [-0.0005, -0.0002, -0.0005, -0.0005, None, -0.0005],
            "v193_account_return_pct": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
            "v193_account_pnl_bps": [100.0, 200.0, 300.0, 400.0, 500.0, 600.0],
        }
    )

    out = module._apply_long_rescue_premium_discount_stepup_policy(trades, policy)

    assert list(out["v194_state_multiplier"]) == [1.25, 1.0, 1.0, 1.0, 1.0, 1.0]
    assert list(out["v194_state_action"]) == [
        "long_rescue_premium_discount_stepup",
        "unchanged",
        "unchanged",
        "unchanged",
        "unchanged",
        "unchanged",
    ]
    assert list(out["v194_account_return_pct"]) == [12.5, 20.0, 30.0, 40.0, 50.0, 60.0]
    assert list(out["v194_account_pnl_bps"]) == [125.0, 200.0, 300.0, 400.0, 500.0, 600.0]


def test_v194_comparison_requires_holdout_and_concentration_gates() -> None:
    module = _load_module()
    timestamps = pd.date_range("2024-01-01T00:00:00Z", periods=40, freq="MS")
    baseline = pd.DataFrame(
        {
            "timestamp": timestamps,
            "v194_policy": ["v193_baseline_no_long_rescue_premium_discount_stepup"] * len(timestamps),
            "v194_account_return_pct": [10.0] * len(timestamps),
            "v194_account_pnl_bps": [1000.0] * len(timestamps),
            "v194_state_action": ["unchanged"] * len(timestamps),
            "v194_state_multiplier": [1.0] * len(timestamps),
        }
    )
    candidate = baseline.copy()
    candidate["v194_policy"] = "candidate"
    candidate["v194_account_return_pct"] = [11.0] * len(timestamps)
    candidate["v194_account_pnl_bps"] = [1100.0] * len(timestamps)
    candidate["v194_state_action"] = ["long_rescue_premium_discount_stepup"] * len(timestamps)
    candidate["v194_state_multiplier"] = [1.25] * len(timestamps)

    comparison = module._compare_policies(
        {"v193_baseline_no_long_rescue_premium_discount_stepup": baseline, "candidate": candidate},
        module._baseline_months(baseline),
    )

    row = comparison.loc[comparison["policy"].eq("candidate")].iloc[0]
    assert row["premium_discount_stepup_passed"] is True
    assert row["stepup_trade_count"] == 40
    assert row["stepup_active_month_count"] == 40
    assert row["stepup_max_month_trade_share_pct"] == 2.5
    assert row["holdout_return_delta_pct"] > 0.0


def test_v194_payload_includes_v193_v194_iteration_metrics() -> None:
    module = _load_module()
    comparison = pd.DataFrame(
        {
            "policy": ["v193_baseline_no_long_rescue_premium_discount_stepup", "candidate"],
            "premium_discount_stepup_passed": [False, True],
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
            "stepup_trade_count": [0, 37],
            "stepup_active_month_count": [0, 9],
            "stepup_max_month_trade_share_pct": [0.0, 29.73],
            "stepup_max_single_trade_delta_share_pct": [0.0, 33.70],
        }
    )

    payload = module._payload_for_comparison(comparison, selected_policy="candidate")

    table = payload["iteration_metrics_table"]
    assert table[0]["version"] == "V193"
    assert table[1]["version"] == "V194"
    assert table[1]["account_return_pct"] == 140.0
    assert table[1]["improvement_pct"] == 40.0
    assert table[1]["positive_months"] == "24/24"
    assert table[1]["holdout_months"] == "6/6"
    assert payload["decision"]["promote_to_live"] is False


def test_v194_baseline_policy_does_not_mark_stepup_actions() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        {
            "side": ["long"],
            "leg": ["rescue"],
            "v188_state_action": ["unchanged"],
            "v189_state_action": ["unchanged"],
            "v190_state_action": ["unchanged"],
            "v191_state_action": ["unchanged"],
            "v192_state_action": ["unchanged"],
            "v193_state_action": ["unchanged"],
            "premium_open": [-0.001],
            "v193_account_return_pct": [10.0],
            "v193_account_pnl_bps": [1000.0],
        }
    )

    out = module._apply_long_rescue_premium_discount_stepup_policy(trades, module.POLICIES[0])

    assert out.iloc[0]["v194_state_action"] == "unchanged"
    assert out.iloc[0]["v194_state_multiplier"] == 1.0
