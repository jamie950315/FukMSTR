from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v195_post_goal_overfitting_audit.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v195_post_goal_overfitting_audit", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v195_iteration_row_exposes_month_and_single_trade_concentration() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2025-12-01T00:00:00Z",
                    "2026-01-02T00:00:00Z",
                    "2026-01-03T00:00:00Z",
                    "2026-02-01T00:00:00Z",
                ],
                utc=True,
            ),
            "prev_return": [10.0, 10.0, 10.0, 10.0],
            "new_return": [11.0, 30.0, 11.0, 10.0],
            "state_action": ["changed", "changed", "changed", "unchanged"],
        }
    )

    row = module._iteration_concentration_row(
        frame,
        version="VX",
        previous_version="VW",
        baseline_return_col="prev_return",
        candidate_return_col="new_return",
        action_col="state_action",
        changed_actions={"changed"},
    )

    assert row["return_delta_pct"] == 22.0
    assert row["holdout_return_delta_pct"] == 21.0
    assert row["affected_trade_count"] == 3
    assert row["affected_active_month_count"] == 2
    assert row["top_delta_month"] == "2026-01"
    assert row["top_month_delta_share_pct"] == 95.45454545454545
    assert row["top_single_delta_share_pct"] == 90.9090909090909


def test_v195_payload_flags_v194_like_overfitting_risk() -> None:
    module = _load_module()
    iteration_table = pd.DataFrame(
        {
            "version": ["V192", "V193", "V194"],
            "return_delta_pct": [13.38, 19.67, 94.04],
            "holdout_return_delta_pct": [7.53, 8.44, 66.60],
            "affected_trade_count": [37, 18, 37],
            "affected_active_month_count": [13, 10, 9],
            "top_month_delta_share_pct": [35.41, 24.04, 62.43],
            "top_single_delta_share_pct": [18.21, 15.83, 33.70],
        }
    )

    payload = module._payload_for_audit(iteration_table)

    assert payload["decision"]["status"] == "post_goal_overfitting_warning"
    assert payload["decision"]["highest_risk_version"] == "V194"
    assert payload["decision"]["stop_historical_optimization"] is True
    assert payload["decision"]["recommendation"] == "freeze_historical_optimization_and_forward_monitor"
    assert payload["decision"]["v194_high_concentration_risk"] is True
    assert payload["config"]["promotes_live_trading"] is False


def test_v195_metrics_table_keeps_required_iteration_metrics() -> None:
    module = _load_module()
    version_metrics = pd.DataFrame(
        {
            "version": ["V193", "V194"],
            "account_return_pct": [3950.66, 4044.70],
            "improvement_pct": ["-", 94.04],
            "max_drawdown_pct": [-30.20, -30.20],
            "positive_months": ["24/24", "24/24"],
            "holdout_return_pct": [1386.21, 1452.80],
            "holdout_months": ["6/6", "6/6"],
        }
    )

    markdown = module._metrics_table_markdown(version_metrics)

    assert "| Account return estimate | +3950.66% | +4044.70% |" in markdown
    assert "| Improvement | - | +94.04 percentage points |" in markdown
    assert "| Holdout months | 6/6 | 6/6 |" in markdown
