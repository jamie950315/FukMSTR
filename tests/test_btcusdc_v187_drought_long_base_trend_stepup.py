from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v187_drought_long_base_trend_stepup.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v187_drought_long_base_trend_stepup", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v187_steps_up_only_unchanged_drought_long_base_deep_60m_rows() -> None:
    module = _load_module()
    policy = module.DroughtLongBaseTrendStepupPolicy(
        policy="example",
        min_trend_abs_60_bps=238.0,
        stepup_multiplier=1.25,
    )
    trades = pd.DataFrame(
        {
            "source": ["v122_drought", "v122_drought", "v120_peak", "v122_drought"],
            "side": ["long", "long", "long", "short"],
            "leg": ["base", "base", "base", "base"],
            "v186_state_action": ["unchanged", "unchanged", "unchanged", "unchanged"],
            "trend_abs_60_bps": [239.0, 237.0, 300.0, 300.0],
            "v186_account_return_pct": [10.0, 20.0, 30.0, 40.0],
            "v186_account_pnl_bps": [100.0, 200.0, 300.0, 400.0],
        }
    )

    out = module._apply_drought_long_base_trend_stepup_policy(trades, policy)

    assert list(out["v187_state_multiplier"]) == [1.25, 1.0, 1.0, 1.0]
    assert list(out["v187_state_action"]) == [
        "drought_long_base_trend_stepup",
        "unchanged",
        "unchanged",
        "unchanged",
    ]
    assert list(out["v187_account_return_pct"]) == [12.5, 20.0, 30.0, 40.0]
    assert list(out["v187_account_pnl_bps"]) == [125.0, 200.0, 300.0, 400.0]


def test_v187_comparison_allows_tiny_float_noise_on_drawdown_gate() -> None:
    module = _load_module()
    timestamps = pd.date_range("2024-01-01T00:00:00Z", periods=40, freq="MS")
    baseline = pd.DataFrame(
        {
            "timestamp": timestamps,
            "v187_policy": ["v186_baseline_no_drought_long_base_trend_stepup"] * len(timestamps),
            "v187_account_return_pct": [10.0] * len(timestamps),
            "v187_account_pnl_bps": [1000.0] * len(timestamps),
            "v187_state_action": ["unchanged"] * len(timestamps),
            "v187_state_multiplier": [1.0] * len(timestamps),
        }
    )
    candidate = baseline.copy()
    candidate["v187_policy"] = "candidate"
    candidate["v187_account_return_pct"] = [11.0] * len(timestamps)
    candidate["v187_account_pnl_bps"] = [1100.0] * len(timestamps)
    candidate["v187_state_action"] = ["drought_long_base_trend_stepup"] * len(timestamps)
    candidate["v187_state_multiplier"] = [1.25] * len(timestamps)

    comparison = module._compare_policies(
        {"v186_baseline_no_drought_long_base_trend_stepup": baseline, "candidate": candidate},
        module._baseline_months(baseline),
    )

    row = comparison.loc[comparison["policy"].eq("candidate")].iloc[0]
    assert row["drought_trend_stepup_passed"] is True
    assert row["stepup_trade_count"] == 40
    assert row["stepup_active_month_count"] == 40
    assert row["stepup_max_month_trade_share_pct"] == 2.5
    assert row["holdout_return_delta_pct"] > 0.0


def test_v187_payload_includes_v186_v187_iteration_metrics() -> None:
    module = _load_module()
    comparison = pd.DataFrame(
        {
            "policy": ["v186_baseline_no_drought_long_base_trend_stepup", "candidate"],
            "drought_trend_stepup_passed": [False, True],
            "total_account_return_pct": [100.0, 130.0],
            "return_delta_pct": [0.0, 30.0],
            "max_drawdown_pct": [-10.0, -10.0],
            "drawdown_improvement_pct": [0.0, 0.0],
            "positive_months": [24, 24],
            "month_count": [24, 24],
            "holdout_return_pct": [30.0, 45.0],
            "holdout_return_delta_pct": [0.0, 15.0],
            "holdout_max_drawdown_improvement_pct": [0.0, 0.0],
            "holdout_positive_months": [6, 6],
            "holdout_month_count": [6, 6],
            "stepup_trade_count": [0, 22],
            "stepup_active_month_count": [0, 11],
            "stepup_max_month_trade_share_pct": [0.0, 27.27],
            "stepup_max_single_trade_delta_share_pct": [0.0, 20.12],
        }
    )

    payload = module._payload_for_comparison(comparison, selected_policy="candidate")

    table = payload["iteration_metrics_table"]
    assert table[0]["version"] == "V186"
    assert table[1]["version"] == "V187"
    assert table[1]["account_return_pct"] == 130.0
    assert table[1]["improvement_pct"] == 30.0
    assert table[1]["positive_months"] == "24/24"
    assert table[1]["holdout_months"] == "6/6"
    assert payload["decision"]["promote_to_live"] is False


def test_v187_baseline_policy_does_not_mark_stepup_actions() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        {
            "source": ["v122_drought"],
            "side": ["long"],
            "leg": ["base"],
            "v186_state_action": ["unchanged"],
            "trend_abs_60_bps": [999.0],
            "v186_account_return_pct": [10.0],
            "v186_account_pnl_bps": [1000.0],
        }
    )

    out = module._apply_drought_long_base_trend_stepup_policy(trades, module.POLICIES[0])

    assert out.iloc[0]["v187_state_action"] == "unchanged"
    assert out.iloc[0]["v187_state_multiplier"] == 1.0
