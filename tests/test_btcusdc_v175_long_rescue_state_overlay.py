from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v175_long_rescue_state_overlay.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v175_long_rescue_state_overlay", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v175_policy_only_scales_long_rescue_state_matches() -> None:
    module = _load_module()
    policy = module.LongRescueStatePolicy(
        policy="example",
        fragile_funding_threshold=-1.5,
        fragile_multiplier=0.25,
        high_confidence_threshold=0.62,
        nonfragile_high_confidence_multiplier=1.2,
    )
    trades = pd.DataFrame(
        {
            "side": ["long", "long", "long", "short", "long"],
            "leg": ["rescue", "rescue", "base", "rescue", "rescue"],
            "funding_z_120d": [-2.0, -0.5, -0.5, -0.5, -0.5],
            "direction_probability": [0.65, 0.63, 0.66, 0.66, 0.61],
            "v162_account_return_pct": [10.0, 20.0, 30.0, 40.0, 50.0],
            "v162_account_pnl_bps": [100.0, 200.0, 300.0, 400.0, 500.0],
        }
    )

    out = module._apply_long_rescue_state_policy(trades, policy)

    assert list(out["v175_state_multiplier"]) == [0.25, 1.2, 1.0, 1.0, 1.0]
    assert list(out["v175_state_action"]) == [
        "fragile_funding_throttle",
        "nonfragile_high_confidence_boost",
        "unchanged",
        "unchanged",
        "unchanged",
    ]


def test_v175_comparison_identifies_growth_candidate_without_drawdown_regression() -> None:
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
            "v175_policy": ["baseline", "baseline", "baseline"],
            "v175_account_return_pct": [100.0, -20.0, 20.0],
            "v175_account_pnl_bps": [1000.0, -200.0, 200.0],
            "v175_state_action": ["unchanged", "unchanged", "unchanged"],
            "v175_state_multiplier": [1.0, 1.0, 1.0],
        }
    )
    boosted = baseline.copy()
    boosted["v175_policy"] = "boosted"
    boosted["v175_account_return_pct"] = [106.0, -20.0, 20.0]
    boosted["v175_account_pnl_bps"] = [1060.0, -200.0, 200.0]
    boosted["v175_state_action"] = ["nonfragile_high_confidence_boost", "unchanged", "unchanged"]
    boosted["v175_state_multiplier"] = [1.06, 1.0, 1.0]

    comparison = module._compare_policies(
        {"v162_baseline_no_state_overlay": baseline, "boosted": boosted},
        module._baseline_months(baseline),
    )

    row = comparison.loc[comparison["policy"].eq("boosted")].iloc[0]
    assert row["growth_passed"] is True
    assert row["return_improvement_rate"] >= module.MIN_RETURN_IMPROVEMENT_RATE
    assert row["drawdown_improvement_pct"] == 0.0


def test_v175_payload_declares_research_overlay_constraints() -> None:
    module = _load_module()
    comparison = pd.DataFrame(
        {
            "policy": ["v162_baseline_no_state_overlay", "v175_nonfragile_high_confidence_boost_1p20"],
            "total_account_return_pct": [100.0, 106.0],
            "max_drawdown_pct": [-10.0, -10.0],
            "worst_month_pct": [1.0, 1.0],
            "executed_trade_count": [10, 10],
            "scaled_trade_count": [0, 3],
            "growth_passed": [False, True],
            "balanced_passed": [False, False],
        }
    )

    payload = module._payload_for_comparison(
        comparison,
        selected_policy="v175_nonfragile_high_confidence_boost_1p20",
    )

    assert payload["config"]["adds_new_trades"] is False
    assert payload["config"]["changes_existing_threshold"] is False
    assert payload["config"]["changes_trade_side"] is False
    assert payload["config"]["promotes_live_trading"] is False
    assert payload["decision"]["status"] == "long_rescue_state_overlay_candidate_ready"
