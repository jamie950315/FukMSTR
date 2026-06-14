from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v173_timestamp_side_exposure_cap.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v173_timestamp_side_exposure_cap", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v173_annotates_timestamp_side_exposure() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        {
            "timestamp": [
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:00:00Z",
            ],
            "side": ["long", "long", "short"],
            "position_weight": [2.0, 3.0, 1.5],
            "v162_account_return_pct": [10.0, -4.0, 2.0],
            "v162_account_pnl_bps": [1000.0, -400.0, 200.0],
        }
    )

    out = module._annotate_timestamp_side_exposure(trades)

    assert list(out["v173_timestamp_side_trade_count"]) == [2, 2, 1]
    assert list(out["v173_timestamp_side_position_weight"].round(6)) == [5.0, 5.0, 1.5]


def test_v173_cap_scales_only_groups_above_cap_without_changing_side() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z", "2024-01-01T00:05:00Z"],
                utc=True,
            ),
            "side": ["long", "long", "long"],
            "position_weight": [2.0, 3.0, 1.0],
            "v162_account_return_pct": [10.0, -4.0, 6.0],
            "v162_account_pnl_bps": [1000.0, -400.0, 600.0],
        }
    )
    annotated = module._annotate_timestamp_side_exposure(trades)
    policy = module.TimestampSideExposurePolicy(policy="cap_3", max_timestamp_side_weight=3.0)

    out = module._apply_timestamp_side_cap(annotated, policy)

    assert list(out["side"]) == ["long", "long", "long"]
    assert list(out["v173_cap_applied"]) == [True, True, False]
    assert list(out["v173_exposure_multiplier"].round(6)) == [0.6, 0.6, 1.0]
    assert list(out["v173_account_return_pct"].round(6)) == [6.0, -2.4, 6.0]


def test_v173_payload_declares_cap_only_behavior() -> None:
    module = _load_module()
    comparison = pd.DataFrame(
        {
            "policy": ["v162_baseline_no_timestamp_side_cap", "candidate"],
            "total_account_return_pct": [100.0, 98.0],
            "max_drawdown_pct": [-20.0, -12.0],
            "worst_month_pct": [-5.0, -3.0],
            "capped_trade_count": [0, 2],
        }
    )

    payload = module._payload_for_comparison(comparison, selected_policy="candidate")

    assert payload["config"]["adds_new_trades"] is False
    assert payload["config"]["changes_existing_threshold"] is False
    assert payload["config"]["changes_trade_side"] is False
    assert payload["config"]["promotes_live_trading"] is False
    assert payload["decision"]["selected_policy"] == "candidate"
    assert payload["decision"]["selected_return_delta_pct"] == -2.0
    assert payload["decision"]["selected_drawdown_improvement_pct"] == 8.0
