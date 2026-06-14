from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v164_v162_robustness_audit.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v164_v162_robustness_audit", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v164_extra_execution_cost_scales_by_leverage_and_position_weight() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        {
            "v162_account_pnl_bps": [100.0, -50.0, 20.0],
            "v162_account_return_pct": [1.0, -0.5, 0.2],
            "account_leverage": [3.0, 2.0, 5.0],
            "position_weight": [1.0, 0.5, 0.2],
        }
    )

    out = module._apply_extra_execution_cost(frame, extra_cost_bps=4.0)

    assert list(out["v164_extra_cost_account_bps"].round(6)) == [12.0, 4.0, 4.0]
    assert list(out["v164_account_pnl_bps"].round(6)) == [88.0, -54.0, 16.0]
    assert list(out["v164_account_return_pct"].round(6)) == [0.88, -0.54, 0.16]


def test_v164_v162_overlay_replay_uses_long_trend_follow_condition() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        {
            "v161_account_return_pct": [10.0, -10.0, 8.0, 6.0],
            "v161_account_pnl_bps": [100.0, -100.0, 80.0, 60.0],
            "side": ["long", "short", "long", "long"],
            "trend_follow_1440_bps": [-10.0, 80.0, -40.0, 5.0],
        }
    )

    out = module._apply_v162_overlay_from_v161(frame, threshold=-29.0, modifier=1.10)

    assert list(out["v164_v162_replay_flag"]) == [True, False, False, True]
    assert list(out["v164_account_return_pct"].round(6)) == [11.0, -10.0, 8.0, 6.6]
    assert list(out["v164_account_pnl_bps"].round(6)) == [110.0, -100.0, 80.0, 66.0]


def test_v164_scenario_pass_requires_positive_full_and_holdout_months() -> None:
    module = _load_module()
    row = {
        "full_return_pct": 1.0,
        "full_positive_months": 2,
        "full_month_count": 2,
        "holdout_return_pct": 1.0,
        "holdout_positive_months": 1,
        "holdout_month_count": 1,
    }

    assert module._scenario_passed(row) is True

    row["holdout_positive_months"] = 0

    assert module._scenario_passed(row) is False
