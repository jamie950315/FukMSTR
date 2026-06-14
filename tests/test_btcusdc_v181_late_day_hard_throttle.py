from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v181_late_day_hard_throttle.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v181_late_day_hard_throttle", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v181_hard_throttles_only_v180_late_day_rows() -> None:
    module = _load_module()
    policy = module.LateDayHardThrottlePolicy(
        policy="example",
        hard_throttle_multiplier=0.0,
    )
    trades = pd.DataFrame(
        {
            "v180_state_action": ["short_base_late_day_throttle", "unchanged"],
            "v179_account_return_pct": [10.0, 20.0],
            "v179_account_pnl_bps": [100.0, 200.0],
            "v180_account_return_pct": [2.5, 20.0],
            "v180_account_pnl_bps": [25.0, 200.0],
        }
    )

    out = module._apply_late_day_hard_throttle_policy(trades, policy)

    assert list(out["v181_state_multiplier"]) == [0.0, 1.0]
    assert list(out["v181_state_action"]) == ["late_day_hard_throttle", "unchanged"]
    assert list(out["v181_account_return_pct"]) == [0.0, 20.0]
    assert list(out["v181_account_pnl_bps"]) == [0.0, 200.0]


def test_v181_comparison_requires_holdout_and_hard_throttle_diversity() -> None:
    module = _load_module()
    timestamps = pd.date_range("2024-01-01T00:00:00Z", periods=40, freq="MS")
    baseline = pd.DataFrame(
        {
            "timestamp": timestamps,
            "v181_policy": ["v180_baseline_no_hard_throttle"] * len(timestamps),
            "v181_account_return_pct": [10.0] * len(timestamps),
            "v181_account_pnl_bps": [1000.0] * len(timestamps),
            "v181_state_action": ["unchanged"] * len(timestamps),
            "v181_state_multiplier": [1.0] * len(timestamps),
        }
    )
    candidate = baseline.copy()
    candidate["v181_policy"] = "candidate"
    candidate["v181_account_return_pct"] = [11.0] * len(timestamps)
    candidate["v181_account_pnl_bps"] = [1100.0] * len(timestamps)
    candidate["v181_state_action"] = ["late_day_hard_throttle"] * len(timestamps)
    candidate["v181_state_multiplier"] = [0.0] * len(timestamps)

    comparison = module._compare_policies(
        {"v180_baseline_no_hard_throttle": baseline, "candidate": candidate},
        module._baseline_months(baseline),
    )

    row = comparison.loc[comparison["policy"].eq("candidate")].iloc[0]
    assert row["hard_throttle_passed"] is True
    assert row["hard_throttled_trade_count"] == 40
    assert row["hard_throttled_active_month_count"] == 40
    assert row["hard_throttled_max_month_trade_share_pct"] == 2.5
    assert row["holdout_return_delta_pct"] > 0.0


def test_v181_payload_keeps_candidate_research_only() -> None:
    module = _load_module()
    comparison = pd.DataFrame(
        {
            "policy": ["v180_baseline_no_hard_throttle", "candidate"],
            "hard_throttle_passed": [False, True],
            "total_account_return_pct": [100.0, 110.0],
            "return_delta_pct": [0.0, 10.0],
            "max_drawdown_pct": [-10.0, -9.0],
            "drawdown_improvement_pct": [0.0, 1.0],
            "holdout_return_delta_pct": [0.0, 2.0],
            "holdout_drawdown_improvement_pct": [0.0, 1.0],
            "hard_throttled_trade_count": [0, 48],
            "hard_throttled_active_month_count": [0, 18],
            "hard_throttled_max_month_trade_share_pct": [0.0, 12.5],
        }
    )

    payload = module._payload_for_comparison(comparison, selected_policy="candidate")

    assert payload["decision"]["status"] == "late_day_hard_throttle_candidate_ready"
    assert payload["decision"]["promote_to_live"] is False
    assert payload["config"]["adds_new_trades"] is False
    assert payload["config"]["changes_trade_side"] is False


def test_v181_baseline_policy_does_not_mark_hard_throttle_actions() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        {
            "v180_state_action": ["short_base_late_day_throttle"],
            "v179_account_return_pct": [10.0],
            "v179_account_pnl_bps": [1000.0],
            "v180_account_return_pct": [2.5],
            "v180_account_pnl_bps": [250.0],
        }
    )

    out = module._apply_late_day_hard_throttle_policy(trades, module.POLICIES[0])

    assert out.iloc[0]["v181_state_action"] == "unchanged"
    assert out.iloc[0]["v181_state_multiplier"] == 1.0
