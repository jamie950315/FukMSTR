from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v190_short_base_prior_rally_stepup.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v190_short_base_prior_rally_stepup", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v190_steps_up_only_unchanged_short_base_prior_rally_rows() -> None:
    module = _load_module()
    policy = module.ShortBasePriorRallyStepupPolicy(
        policy="example",
        min_prior_ret_720_bps=138.0,
        stepup_multiplier=1.25,
    )
    trades = pd.DataFrame(
        {
            "side": ["short", "short", "short", "long", "short", "short"],
            "leg": ["base", "base", "base", "base", "rescue", "base"],
            "v188_state_action": [
                "unchanged",
                "unchanged",
                "drought_trend_emotion_stepup",
                "unchanged",
                "unchanged",
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
            "prior_ret_720_bps": [150.0, 100.0, 160.0, 170.0, 180.0, 190.0],
            "v189_account_return_pct": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
            "v189_account_pnl_bps": [100.0, 200.0, 300.0, 400.0, 500.0, 600.0],
        }
    )

    out = module._apply_short_base_prior_rally_stepup_policy(trades, policy)

    assert list(out["v190_state_multiplier"]) == [1.25, 1.0, 1.0, 1.0, 1.0, 1.0]
    assert list(out["v190_state_action"]) == [
        "short_base_prior_rally_stepup",
        "unchanged",
        "unchanged",
        "unchanged",
        "unchanged",
        "unchanged",
    ]
    assert list(out["v190_account_return_pct"]) == [12.5, 20.0, 30.0, 40.0, 50.0, 60.0]
    assert list(out["v190_account_pnl_bps"]) == [125.0, 200.0, 300.0, 400.0, 500.0, 600.0]


def test_v190_comparison_requires_holdout_and_concentration_gates() -> None:
    module = _load_module()
    timestamps = pd.date_range("2024-01-01T00:00:00Z", periods=40, freq="MS")
    baseline = pd.DataFrame(
        {
            "timestamp": timestamps,
            "v190_policy": ["v189_baseline_no_short_base_prior_rally_stepup"] * len(timestamps),
            "v190_account_return_pct": [10.0] * len(timestamps),
            "v190_account_pnl_bps": [1000.0] * len(timestamps),
            "v190_state_action": ["unchanged"] * len(timestamps),
            "v190_state_multiplier": [1.0] * len(timestamps),
        }
    )
    candidate = baseline.copy()
    candidate["v190_policy"] = "candidate"
    candidate["v190_account_return_pct"] = [11.0] * len(timestamps)
    candidate["v190_account_pnl_bps"] = [1100.0] * len(timestamps)
    candidate["v190_state_action"] = ["short_base_prior_rally_stepup"] * len(timestamps)
    candidate["v190_state_multiplier"] = [1.25] * len(timestamps)

    comparison = module._compare_policies(
        {"v189_baseline_no_short_base_prior_rally_stepup": baseline, "candidate": candidate},
        module._baseline_months(baseline),
    )

    row = comparison.loc[comparison["policy"].eq("candidate")].iloc[0]
    assert row["prior_rally_stepup_passed"] is True
    assert row["stepup_trade_count"] == 40
    assert row["stepup_active_month_count"] == 40
    assert row["stepup_max_month_trade_share_pct"] == 2.5
    assert row["holdout_return_delta_pct"] > 0.0


def test_v190_payload_includes_v189_v190_iteration_metrics() -> None:
    module = _load_module()
    comparison = pd.DataFrame(
        {
            "policy": ["v189_baseline_no_short_base_prior_rally_stepup", "candidate"],
            "prior_rally_stepup_passed": [False, True],
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
            "stepup_trade_count": [0, 73],
            "stepup_active_month_count": [0, 22],
            "stepup_max_month_trade_share_pct": [0.0, 10.96],
            "stepup_max_single_trade_delta_share_pct": [0.0, 23.37],
        }
    )

    payload = module._payload_for_comparison(comparison, selected_policy="candidate")

    table = payload["iteration_metrics_table"]
    assert table[0]["version"] == "V189"
    assert table[1]["version"] == "V190"
    assert table[1]["account_return_pct"] == 140.0
    assert table[1]["improvement_pct"] == 40.0
    assert table[1]["positive_months"] == "24/24"
    assert table[1]["holdout_months"] == "6/6"
    assert payload["decision"]["promote_to_live"] is False


def test_v190_baseline_policy_does_not_mark_stepup_actions() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        {
            "side": ["short"],
            "leg": ["base"],
            "v188_state_action": ["unchanged"],
            "v189_state_action": ["unchanged"],
            "prior_ret_720_bps": [999.0],
            "v189_account_return_pct": [10.0],
            "v189_account_pnl_bps": [1000.0],
        }
    )

    out = module._apply_short_base_prior_rally_stepup_policy(trades, module.POLICIES[0])

    assert out.iloc[0]["v190_state_action"] == "unchanged"
    assert out.iloc[0]["v190_state_multiplier"] == 1.0
