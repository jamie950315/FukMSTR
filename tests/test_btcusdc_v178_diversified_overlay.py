from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v178_diversified_overlay.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v178_diversified_overlay", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v178_policy_boosts_only_nonfragile_diversified_long_rescue() -> None:
    module = _load_module()
    policy = module.DiversifiedOverlayPolicy(
        policy="example",
        fragile_funding_threshold=-1.5,
        fragile_premium_threshold=-2.0,
        fragile_multiplier=0.5,
        probability_threshold=0.61,
        min_range_position_720=0.005,
        boost_multiplier=1.25,
    )
    trades = pd.DataFrame(
        {
            "side": ["long", "long", "long", "long", "short"],
            "leg": ["rescue", "rescue", "rescue", "rescue", "rescue"],
            "funding_z_120d": [-2.0, -0.2, -0.2, -0.2, -0.2],
            "premium_z_30d": [-0.5, -2.5, -0.5, -0.5, -0.5],
            "direction_probability": [0.70, 0.70, 0.62, 0.62, 0.62],
            "prior_range_pos_720": [0.02, 0.02, 0.006, 0.001, 0.006],
            "v162_account_return_pct": [10.0, 20.0, 30.0, 40.0, 50.0],
            "v162_account_pnl_bps": [100.0, 200.0, 300.0, 400.0, 500.0],
        }
    )

    out = module._apply_diversified_overlay_policy(trades, policy)

    assert list(out["v178_state_multiplier"]) == [0.5, 0.5, 1.25, 1.0, 1.0]
    assert list(out["v178_state_action"]) == [
        "fragile_state_throttle",
        "fragile_state_throttle",
        "diversified_high_confidence_boost",
        "unchanged",
        "unchanged",
    ]


def test_v178_comparison_requires_diversity_and_holdout() -> None:
    module = _load_module()
    timestamps = pd.date_range("2025-01-01T00:00:00Z", periods=20, freq="MS")
    baseline = pd.DataFrame(
        {
            "timestamp": timestamps,
            "v178_policy": ["v162_baseline_no_diversified_overlay"] * len(timestamps),
            "v178_account_return_pct": [10.0] * len(timestamps),
            "v178_account_pnl_bps": [1000.0] * len(timestamps),
            "v178_state_action": ["unchanged"] * len(timestamps),
            "v178_state_multiplier": [1.0] * len(timestamps),
        }
    )
    candidate = baseline.copy()
    candidate["v178_policy"] = "candidate"
    candidate["v178_account_return_pct"] = [11.0] * len(timestamps)
    candidate["v178_account_pnl_bps"] = [1100.0] * len(timestamps)
    candidate["v178_state_action"] = ["diversified_high_confidence_boost"] * len(timestamps)
    candidate["v178_state_multiplier"] = [1.1] * len(timestamps)

    comparison = module._compare_policies(
        {"v162_baseline_no_diversified_overlay": baseline, "candidate": candidate},
        module._baseline_months(baseline),
    )

    row = comparison.loc[comparison["policy"].eq("candidate")].iloc[0]
    assert row["diversified_passed"] is True
    assert row["boosted_trade_count"] == 20
    assert row["boosted_active_month_count"] == 20
    assert row["boosted_max_month_trade_share_pct"] == 5.0
    assert row["holdout_return_delta_pct"] > 0.0


def test_v178_payload_keeps_candidate_research_only() -> None:
    module = _load_module()
    comparison = pd.DataFrame(
        {
            "policy": ["v162_baseline_no_diversified_overlay", "candidate"],
            "diversified_passed": [False, True],
            "total_account_return_pct": [100.0, 110.0],
            "return_delta_pct": [0.0, 10.0],
            "max_drawdown_pct": [-10.0, -9.0],
            "drawdown_improvement_pct": [0.0, 1.0],
            "holdout_return_delta_pct": [0.0, 2.0],
            "boosted_trade_count": [0, 33],
            "boosted_active_month_count": [0, 12],
            "boosted_max_month_trade_share_pct": [0.0, 24.0],
        }
    )

    payload = module._payload_for_comparison(comparison, selected_policy="candidate")

    assert payload["decision"]["status"] == "diversified_overlay_candidate_ready"
    assert payload["decision"]["promote_to_live"] is False
    assert payload["config"]["adds_new_trades"] is False
    assert payload["config"]["changes_trade_side"] is False


def test_v178_baseline_policy_does_not_mark_boost_actions() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        {
            "side": ["long"],
            "leg": ["rescue"],
            "funding_z_120d": [0.0],
            "premium_z_30d": [0.0],
            "direction_probability": [0.90],
            "prior_range_pos_720": [0.50],
            "v162_account_return_pct": [10.0],
            "v162_account_pnl_bps": [1000.0],
        }
    )

    out = module._apply_diversified_overlay_policy(trades, module.POLICIES[0])

    assert out.iloc[0]["v178_state_action"] == "unchanged"
    assert out.iloc[0]["v178_state_multiplier"] == 1.0
