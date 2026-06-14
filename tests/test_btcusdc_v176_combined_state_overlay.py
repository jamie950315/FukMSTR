from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v176_combined_state_overlay.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v176_combined_state_overlay", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v176_policy_uses_funding_or_premium_fragile_state_before_boosting() -> None:
    module = _load_module()
    policy = module.CombinedStatePolicy(
        policy="example",
        fragile_funding_threshold=-1.5,
        fragile_premium_threshold=-2.0,
        fragile_multiplier=0.25,
        high_confidence_threshold=0.64,
        high_confidence_multiplier=1.35,
    )
    trades = pd.DataFrame(
        {
            "side": ["long", "long", "long", "long", "short"],
            "leg": ["rescue", "rescue", "rescue", "rescue", "rescue"],
            "funding_z_120d": [-2.0, -0.2, -0.2, -0.2, -0.2],
            "premium_z_30d": [-0.5, -2.5, -0.5, -0.5, -0.5],
            "direction_probability": [0.70, 0.70, 0.65, 0.63, 0.70],
            "v162_account_return_pct": [10.0, 20.0, 30.0, 40.0, 50.0],
            "v162_account_pnl_bps": [100.0, 200.0, 300.0, 400.0, 500.0],
        }
    )

    out = module._apply_combined_state_policy(trades, policy)

    assert list(out["v176_state_multiplier"]) == [0.25, 0.25, 1.35, 1.0, 1.0]
    assert list(out["v176_state_action"]) == [
        "fragile_state_throttle",
        "fragile_state_throttle",
        "nonfragile_high_confidence_boost",
        "unchanged",
        "unchanged",
    ]


def test_v176_comparison_requires_return_and_drawdown_improvement() -> None:
    module = _load_module()
    baseline = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2024-01-01T00:00:00Z",
                    "2024-01-01T00:05:00Z",
                    "2024-01-01T00:10:00Z",
                ],
                utc=True,
            ),
            "v176_policy": ["v162_baseline_no_combined_overlay"] * 3,
            "v176_account_return_pct": [100.0, -40.0, 40.0],
            "v176_account_pnl_bps": [1000.0, -400.0, 400.0],
            "v176_state_action": ["unchanged"] * 3,
            "v176_state_multiplier": [1.0, 1.0, 1.0],
        }
    )
    combined = baseline.copy()
    combined["v176_policy"] = "combined"
    combined["v176_account_return_pct"] = [106.0, -35.0, 40.0]
    combined["v176_account_pnl_bps"] = [1060.0, -350.0, 400.0]
    combined["v176_state_action"] = ["nonfragile_high_confidence_boost", "fragile_state_throttle", "unchanged"]
    combined["v176_state_multiplier"] = [1.06, 0.875, 1.0]

    comparison = module._compare_policies(
        {"v162_baseline_no_combined_overlay": baseline, "combined": combined},
        module._baseline_months(baseline),
    )

    row = comparison.loc[comparison["policy"].eq("combined")].iloc[0]
    assert row["combined_passed"] is True
    assert row["return_improvement_rate"] >= module.MIN_RETURN_IMPROVEMENT_RATE
    assert row["drawdown_improvement_pct"] >= module.MIN_DRAWDOWN_IMPROVEMENT_PCT


def test_v176_payload_declares_no_entry_rule_changes() -> None:
    module = _load_module()
    comparison = pd.DataFrame(
        {
            "policy": ["v162_baseline_no_combined_overlay", "combined"],
            "total_account_return_pct": [100.0, 106.0],
            "max_drawdown_pct": [-10.0, -6.5],
            "worst_month_pct": [1.0, 1.0],
            "scaled_trade_count": [0, 2],
            "combined_passed": [False, True],
            "return_improvement_rate": [0.0, 0.06],
        }
    )

    payload = module._payload_for_comparison(comparison, selected_policy="combined")

    assert payload["config"]["adds_new_trades"] is False
    assert payload["config"]["changes_existing_threshold"] is False
    assert payload["config"]["changes_trade_side"] is False
    assert payload["config"]["promotes_live_trading"] is False
    assert payload["decision"]["status"] == "combined_state_overlay_candidate_ready"
