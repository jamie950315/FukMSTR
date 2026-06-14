from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v177_v176_stability_audit.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v177_v176_stability_audit", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v177_period_metrics_compare_candidate_to_baseline() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2025-12-01T00:00:00Z",
                    "2025-12-02T00:00:00Z",
                    "2026-01-02T00:00:00Z",
                ],
                utc=True,
            ),
            "v162_account_return_pct": [10.0, -5.0, 5.0],
            "v176_account_return_pct": [12.0, -4.0, 5.0],
            "v162_account_pnl_bps": [1000.0, -500.0, 500.0],
            "v176_account_pnl_bps": [1200.0, -400.0, 500.0],
        }
    )

    table = module._period_stability_table(frame)

    selector = table.loc[table["period"].eq("selector")].iloc[0]
    assert selector["candidate_return_pct"] == 8.0
    assert selector["baseline_return_pct"] == 5.0
    assert selector["return_delta_pct"] == 3.0
    assert selector["candidate_max_drawdown_pct"] == -4.0


def test_v177_action_profile_exposes_boost_concentration() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2025-01-01T00:00:00Z",
                    "2025-01-02T00:00:00Z",
                    "2025-02-01T00:00:00Z",
                ],
                utc=True,
            ),
            "v176_state_action": [
                "nonfragile_high_confidence_boost",
                "nonfragile_high_confidence_boost",
                "fragile_state_throttle",
            ],
            "v162_account_return_pct": [10.0, 20.0, -8.0],
            "v176_account_return_pct": [13.5, 27.0, -2.0],
            "v176_account_pnl_bps": [1350.0, 2700.0, -200.0],
        }
    )

    profile = module._action_contribution_profile(frame)

    boosted = profile.loc[profile["v176_state_action"].eq("nonfragile_high_confidence_boost")].iloc[0]
    assert boosted["trade_count"] == 2
    assert boosted["return_delta_pct"] == 10.5
    assert boosted["active_month_count"] == 1
    assert boosted["max_month_trade_share_pct"] == 100.0


def test_v177_payload_flags_small_boost_sample_risk() -> None:
    module = _load_module()
    period_table = pd.DataFrame(
        {
            "period": ["full", "selector", "holdout"],
            "return_delta_pct": [100.0, 80.0, 20.0],
            "drawdown_improvement_pct": [3.5, 2.0, 1.0],
        }
    )
    action_profile = pd.DataFrame(
        {
            "v176_state_action": ["nonfragile_high_confidence_boost"],
            "trade_count": [7],
            "active_month_count": [4],
            "max_month_trade_share_pct": [42.0],
            "return_delta_pct": [140.0],
        }
    )

    payload = module._payload_for_audit(period_table, action_profile)

    assert payload["decision"]["status"] == "v176_stability_warning"
    assert payload["decision"]["boosted_trade_count"] == 7
    assert payload["decision"]["small_boost_sample_risk"] is True
    assert payload["config"]["promotes_live_trading"] is False
