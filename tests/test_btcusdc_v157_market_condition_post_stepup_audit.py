from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v157_market_condition_post_stepup_audit.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v157_market_condition_post_stepup_audit", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v157_feature_candidates_exclude_generated_policy_columns() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        {
            "trend_abs_60_bps": list(range(10)),
            "funding_z_120d": [x / 10 for x in range(10)],
            "v156_account_return_pct": list(range(10)),
            "v156_modifier": [1.0] * 10,
            "v156_base_long_premium_stepup_flag": [False] * 10,
            "timestamp": pd.date_range("2025-01-01", periods=10, tz="UTC"),
        }
    )

    assert module._candidate_features(frame, min_non_null=8, min_unique=8) == [
        "trend_abs_60_bps",
        "funding_z_120d",
    ]


def test_v157_gate_rejects_profit_candidate_with_worse_drawdown() -> None:
    module = _load_module()
    baseline = {
        "full": {
            "total_account_return_pct": 100.0,
            "max_drawdown_pct": -10.0,
            "worst_month_pct": 0.1,
            "positive_months": 3,
            "month_count": 3,
        },
        "selector": {
            "total_account_return_pct": 80.0,
            "max_drawdown_pct": -9.0,
            "worst_month_pct": 0.1,
            "positive_months": 2,
            "month_count": 2,
        },
        "holdout": {
            "total_account_return_pct": 20.0,
            "max_drawdown_pct": -8.0,
            "worst_month_pct": 0.1,
            "positive_months": 1,
            "month_count": 1,
        },
    }
    candidate = {
        "changed_selector_count": 60,
        "changed_holdout_count": 20,
        "full_return_pct": 101.0,
        "full_max_drawdown_pct": -10.1,
        "full_worst_month_pct": 0.1,
        "full_positive_months": 3,
        "full_month_count": 3,
        "selector_return_pct": 81.0,
        "selector_max_drawdown_pct": -9.0,
        "selector_worst_month_pct": 0.1,
        "selector_positive_months": 2,
        "selector_month_count": 2,
        "holdout_return_pct": 21.0,
        "holdout_max_drawdown_pct": -8.0,
        "holdout_worst_month_pct": 0.1,
        "holdout_positive_months": 1,
        "holdout_month_count": 1,
    }

    assert module._passes_strict_gate(candidate, baseline) is False

    candidate["full_max_drawdown_pct"] = -10.0

    assert module._passes_strict_gate(candidate, baseline) is True


def test_v157_rejection_reason_prioritizes_risk_before_return() -> None:
    module = _load_module()
    baseline = {
        "full": {"total_account_return_pct": 100.0, "max_drawdown_pct": -10.0, "worst_month_pct": 0.1},
        "selector": {"total_account_return_pct": 80.0, "max_drawdown_pct": -9.0, "worst_month_pct": 0.1},
        "holdout": {"total_account_return_pct": 20.0, "max_drawdown_pct": -8.0, "worst_month_pct": 0.1},
    }
    candidate = {
        "full_return_pct": 99.0,
        "full_max_drawdown_pct": -10.5,
        "full_worst_month_pct": 0.0,
        "selector_return_pct": 79.0,
        "selector_max_drawdown_pct": -9.0,
        "selector_worst_month_pct": 0.1,
        "holdout_return_pct": 21.0,
        "holdout_max_drawdown_pct": -8.0,
        "holdout_worst_month_pct": 0.1,
    }

    assert module._rejection_reason(candidate, baseline) == "full_drawdown_worse"
