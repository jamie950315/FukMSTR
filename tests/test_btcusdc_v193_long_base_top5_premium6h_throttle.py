from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v193_long_base_top5_premium6h_throttle.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v193_long_base_top5_premium6h_throttle", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v193_throttles_only_unchanged_top5_long_base_high_premium6h_rows() -> None:
    module = _load_module()
    policy = module.LongBaseTop5Premium6hThrottlePolicy(
        policy="example",
        min_premium_close_bps_6h=-4.576517,
        throttle_multiplier=0.0,
    )
    trades = pd.DataFrame(
        {
            "indicator_key": [
                "v125_top5_lb14_strict",
                "v125_top5_lb14_strict",
                "v125_top7_lb14_coverage",
                "v125_top5_lb14_strict",
                "v125_top5_lb14_strict",
                "v125_top5_lb14_strict",
            ],
            "side": ["long", "long", "long", "short", "long", "long"],
            "leg": ["base", "base", "base", "base", "rescue", "base"],
            "v188_state_action": ["unchanged"] * 6,
            "v189_state_action": ["unchanged"] * 6,
            "v190_state_action": ["unchanged"] * 6,
            "v191_state_action": ["unchanged"] * 6,
            "v192_state_action": [
                "unchanged",
                "unchanged",
                "unchanged",
                "unchanged",
                "unchanged",
                "long_base_low_probz_throttle",
            ],
            "premium_close_bps_6h": [-4.0, -5.0, -4.0, -4.0, -4.0, -4.0],
            "v192_account_return_pct": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
            "v192_account_pnl_bps": [100.0, 200.0, 300.0, 400.0, 500.0, 600.0],
        }
    )

    out = module._apply_long_base_top5_premium6h_throttle_policy(trades, policy)

    assert list(out["v193_state_multiplier"]) == [0.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    assert list(out["v193_state_action"]) == [
        "long_base_top5_premium6h_throttle",
        "unchanged",
        "unchanged",
        "unchanged",
        "unchanged",
        "unchanged",
    ]
    assert list(out["v193_account_return_pct"]) == [0.0, 20.0, 30.0, 40.0, 50.0, 60.0]
    assert list(out["v193_account_pnl_bps"]) == [0.0, 200.0, 300.0, 400.0, 500.0, 600.0]


def test_v193_comparison_requires_holdout_and_concentration_gates() -> None:
    module = _load_module()
    timestamps = pd.date_range("2024-01-01T00:00:00Z", periods=40, freq="MS")
    baseline = pd.DataFrame(
        {
            "timestamp": timestamps,
            "v193_policy": ["v192_baseline_no_long_base_top5_premium6h_throttle"] * len(timestamps),
            "v193_account_return_pct": [10.0] * len(timestamps),
            "v193_account_pnl_bps": [1000.0] * len(timestamps),
            "v193_state_action": ["unchanged"] * len(timestamps),
            "v193_state_multiplier": [1.0] * len(timestamps),
        }
    )
    candidate = baseline.copy()
    candidate["v193_policy"] = "candidate"
    candidate["v193_account_return_pct"] = [11.0] * len(timestamps)
    candidate["v193_account_pnl_bps"] = [1100.0] * len(timestamps)
    candidate["v193_state_action"] = ["long_base_top5_premium6h_throttle"] * len(timestamps)
    candidate["v193_state_multiplier"] = [0.0] * len(timestamps)

    comparison = module._compare_policies(
        {"v192_baseline_no_long_base_top5_premium6h_throttle": baseline, "candidate": candidate},
        module._baseline_months(baseline),
    )

    row = comparison.loc[comparison["policy"].eq("candidate")].iloc[0]
    assert row["top5_premium6h_throttle_passed"] is True
    assert row["throttle_trade_count"] == 40
    assert row["throttle_active_month_count"] == 40
    assert row["throttle_max_month_trade_share_pct"] == 2.5
    assert row["holdout_return_delta_pct"] > 0.0


def test_v193_payload_includes_v192_v193_iteration_metrics() -> None:
    module = _load_module()
    comparison = pd.DataFrame(
        {
            "policy": ["v192_baseline_no_long_base_top5_premium6h_throttle", "candidate"],
            "top5_premium6h_throttle_passed": [False, True],
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
            "throttle_trade_count": [0, 18],
            "throttle_active_month_count": [0, 10],
            "throttle_max_month_trade_share_pct": [0.0, 16.67],
            "throttle_max_single_trade_delta_share_pct": [0.0, 15.83],
        }
    )

    payload = module._payload_for_comparison(comparison, selected_policy="candidate")

    table = payload["iteration_metrics_table"]
    assert table[0]["version"] == "V192"
    assert table[1]["version"] == "V193"
    assert table[1]["account_return_pct"] == 140.0
    assert table[1]["improvement_pct"] == 40.0
    assert table[1]["positive_months"] == "24/24"
    assert table[1]["holdout_months"] == "6/6"
    assert payload["decision"]["promote_to_live"] is False


def test_v193_baseline_policy_does_not_mark_throttle_actions() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        {
            "indicator_key": ["v125_top5_lb14_strict"],
            "side": ["long"],
            "leg": ["base"],
            "v188_state_action": ["unchanged"],
            "v189_state_action": ["unchanged"],
            "v190_state_action": ["unchanged"],
            "v191_state_action": ["unchanged"],
            "v192_state_action": ["unchanged"],
            "premium_close_bps_6h": [0.0],
            "v192_account_return_pct": [10.0],
            "v192_account_pnl_bps": [1000.0],
        }
    )

    out = module._apply_long_base_top5_premium6h_throttle_policy(trades, module.POLICIES[0])

    assert out.iloc[0]["v193_state_action"] == "unchanged"
    assert out.iloc[0]["v193_state_multiplier"] == 1.0
