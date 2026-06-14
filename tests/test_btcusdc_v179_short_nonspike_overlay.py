from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v179_short_nonspike_overlay.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v179_short_nonspike_overlay", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v179_policy_boosts_only_short_nonspike_trades() -> None:
    module = _load_module()
    policy = module.ShortNonspikeOverlayPolicy(
        policy="example",
        max_prob_vs_day_sofar=0.01,
        boost_multiplier=1.25,
    )
    trades = pd.DataFrame(
        {
            "side": ["short", "short", "long", "short"],
            "leg": ["base", "rescue", "base", "base"],
            "prob_vs_day_sofar_max": [0.00, 0.011, -0.10, None],
            "v178_account_return_pct": [10.0, 20.0, 30.0, 40.0],
            "v178_account_pnl_bps": [100.0, 200.0, 300.0, 400.0],
        }
    )

    out = module._apply_short_nonspike_overlay_policy(trades, policy)

    assert list(out["v179_state_multiplier"]) == [1.25, 1.0, 1.0, 1.0]
    assert list(out["v179_state_action"]) == [
        "short_nonspike_confidence_boost",
        "unchanged",
        "unchanged",
        "unchanged",
    ]
    assert list(out["v179_account_return_pct"]) == [12.5, 20.0, 30.0, 40.0]
    assert list(out["v179_account_pnl_bps"]) == [125.0, 200.0, 300.0, 400.0]


def test_v179_comparison_requires_short_boost_diversity_and_holdout() -> None:
    module = _load_module()
    timestamps = pd.date_range("2024-01-01T00:00:00Z", periods=40, freq="MS")
    baseline = pd.DataFrame(
        {
            "timestamp": timestamps,
            "v179_policy": ["v178_baseline_no_short_nonspike_overlay"] * len(timestamps),
            "v179_account_return_pct": [10.0] * len(timestamps),
            "v179_account_pnl_bps": [1000.0] * len(timestamps),
            "v179_state_action": ["unchanged"] * len(timestamps),
            "v179_state_multiplier": [1.0] * len(timestamps),
        }
    )
    candidate = baseline.copy()
    candidate["v179_policy"] = "candidate"
    candidate["v179_account_return_pct"] = [11.0] * len(timestamps)
    candidate["v179_account_pnl_bps"] = [1100.0] * len(timestamps)
    candidate["v179_state_action"] = ["short_nonspike_confidence_boost"] * len(timestamps)
    candidate["v179_state_multiplier"] = [1.1] * len(timestamps)

    comparison = module._compare_policies(
        {"v178_baseline_no_short_nonspike_overlay": baseline, "candidate": candidate},
        module._baseline_months(baseline),
    )

    row = comparison.loc[comparison["policy"].eq("candidate")].iloc[0]
    assert row["short_overlay_passed"] is True
    assert row["boosted_trade_count"] == 40
    assert row["boosted_active_month_count"] == 40
    assert row["boosted_max_month_trade_share_pct"] == 2.5
    assert row["holdout_return_delta_pct"] > 0.0


def test_v179_payload_keeps_short_overlay_research_only() -> None:
    module = _load_module()
    comparison = pd.DataFrame(
        {
            "policy": ["v178_baseline_no_short_nonspike_overlay", "candidate"],
            "short_overlay_passed": [False, True],
            "total_account_return_pct": [100.0, 110.0],
            "return_delta_pct": [0.0, 10.0],
            "max_drawdown_pct": [-10.0, -9.0],
            "drawdown_improvement_pct": [0.0, 1.0],
            "holdout_return_delta_pct": [0.0, 2.0],
            "holdout_drawdown_improvement_pct": [0.0, 1.0],
            "boosted_trade_count": [0, 59],
            "boosted_active_month_count": [0, 18],
            "boosted_max_month_trade_share_pct": [0.0, 14.0],
        }
    )

    payload = module._payload_for_comparison(comparison, selected_policy="candidate")

    assert payload["decision"]["status"] == "short_nonspike_overlay_candidate_ready"
    assert payload["decision"]["promote_to_live"] is False
    assert payload["config"]["adds_new_trades"] is False
    assert payload["config"]["changes_trade_side"] is False


def test_v179_baseline_policy_does_not_mark_boost_actions() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        {
            "side": ["short"],
            "leg": ["base"],
            "prob_vs_day_sofar_max": [-0.10],
            "v178_account_return_pct": [10.0],
            "v178_account_pnl_bps": [1000.0],
        }
    )

    out = module._apply_short_nonspike_overlay_policy(trades, module.POLICIES[0])

    assert out.iloc[0]["v179_state_action"] == "unchanged"
    assert out.iloc[0]["v179_state_multiplier"] == 1.0
