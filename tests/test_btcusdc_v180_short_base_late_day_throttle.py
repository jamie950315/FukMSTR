from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v180_short_base_late_day_throttle.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v180_short_base_late_day_throttle", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v180_throttles_only_unchanged_late_day_short_base() -> None:
    module = _load_module()
    policy = module.ShortBaseLateDayThrottlePolicy(
        policy="example",
        min_day_sofar_count=5,
        throttle_multiplier=0.25,
    )
    trades = pd.DataFrame(
        {
            "side": ["short", "short", "short", "long", "short"],
            "leg": ["base", "base", "rescue", "base", "base"],
            "v179_state_action": ["unchanged", "short_nonspike_confidence_boost", "unchanged", "unchanged", "unchanged"],
            "day_sofar_count": [5, 5, 5, 5, 4],
            "v179_account_return_pct": [10.0, 20.0, 30.0, 40.0, 50.0],
            "v179_account_pnl_bps": [100.0, 200.0, 300.0, 400.0, 500.0],
        }
    )

    out = module._apply_short_base_late_day_policy(trades, policy)

    assert list(out["v180_state_multiplier"]) == [0.25, 1.0, 1.0, 1.0, 1.0]
    assert list(out["v180_state_action"]) == [
        "short_base_late_day_throttle",
        "unchanged",
        "unchanged",
        "unchanged",
        "unchanged",
    ]
    assert list(out["v180_account_return_pct"]) == [2.5, 20.0, 30.0, 40.0, 50.0]
    assert list(out["v180_account_pnl_bps"]) == [25.0, 200.0, 300.0, 400.0, 500.0]


def test_v180_comparison_requires_holdout_and_throttle_diversity() -> None:
    module = _load_module()
    timestamps = pd.date_range("2024-01-01T00:00:00Z", periods=40, freq="MS")
    baseline = pd.DataFrame(
        {
            "timestamp": timestamps,
            "v180_policy": ["v179_baseline_no_late_day_throttle"] * len(timestamps),
            "v180_account_return_pct": [10.0] * len(timestamps),
            "v180_account_pnl_bps": [1000.0] * len(timestamps),
            "v180_state_action": ["unchanged"] * len(timestamps),
            "v180_state_multiplier": [1.0] * len(timestamps),
        }
    )
    candidate = baseline.copy()
    candidate["v180_policy"] = "candidate"
    candidate["v180_account_return_pct"] = [11.0] * len(timestamps)
    candidate["v180_account_pnl_bps"] = [1100.0] * len(timestamps)
    candidate["v180_state_action"] = ["short_base_late_day_throttle"] * len(timestamps)
    candidate["v180_state_multiplier"] = [0.25] * len(timestamps)

    comparison = module._compare_policies(
        {"v179_baseline_no_late_day_throttle": baseline, "candidate": candidate},
        module._baseline_months(baseline),
    )

    row = comparison.loc[comparison["policy"].eq("candidate")].iloc[0]
    assert row["late_day_throttle_passed"] is True
    assert row["throttled_trade_count"] == 40
    assert row["throttled_active_month_count"] == 40
    assert row["throttled_max_month_trade_share_pct"] == 2.5
    assert row["holdout_return_delta_pct"] > 0.0


def test_v180_payload_keeps_candidate_research_only() -> None:
    module = _load_module()
    comparison = pd.DataFrame(
        {
            "policy": ["v179_baseline_no_late_day_throttle", "candidate"],
            "late_day_throttle_passed": [False, True],
            "total_account_return_pct": [100.0, 110.0],
            "return_delta_pct": [0.0, 10.0],
            "max_drawdown_pct": [-10.0, -9.0],
            "drawdown_improvement_pct": [0.0, 1.0],
            "holdout_return_delta_pct": [0.0, 2.0],
            "holdout_drawdown_improvement_pct": [0.0, 1.0],
            "throttled_trade_count": [0, 48],
            "throttled_active_month_count": [0, 18],
            "throttled_max_month_trade_share_pct": [0.0, 12.5],
        }
    )

    payload = module._payload_for_comparison(comparison, selected_policy="candidate")

    assert payload["decision"]["status"] == "late_day_throttle_candidate_ready"
    assert payload["decision"]["promote_to_live"] is False
    assert payload["config"]["adds_new_trades"] is False
    assert payload["config"]["changes_trade_side"] is False


def test_v180_baseline_policy_does_not_mark_throttle_actions() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        {
            "side": ["short"],
            "leg": ["base"],
            "v179_state_action": ["unchanged"],
            "day_sofar_count": [99],
            "v179_account_return_pct": [10.0],
            "v179_account_pnl_bps": [1000.0],
        }
    )

    out = module._apply_short_base_late_day_policy(trades, module.POLICIES[0])

    assert out.iloc[0]["v180_state_action"] == "unchanged"
    assert out.iloc[0]["v180_state_multiplier"] == 1.0
