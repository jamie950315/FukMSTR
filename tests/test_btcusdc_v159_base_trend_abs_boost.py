from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v159_base_trend_abs_boost.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v159_base_trend_abs_boost", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v159_spec_uses_selector_base_trend_abs_quantile() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2025-01-01T00:00:00Z",
                    "2025-01-02T00:00:00Z",
                    "2025-01-03T00:00:00Z",
                    "2025-01-04T00:00:00Z",
                    "2025-01-05T00:00:00Z",
                    "2025-01-06T00:00:00Z",
                    "2025-01-07T00:00:00Z",
                    "2025-01-08T00:00:00Z",
                    "2026-01-01T00:00:00Z",
                ],
                utc=True,
            ),
            "leg": ["base"] * 9,
            "side": ["long"] * 9,
            "trend_abs_1440_bps": [100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 9999.0],
        }
    )
    selector_mask = frame["timestamp"] < pd.Timestamp("2026-01-01T00:00:00Z")

    spec = module._overlay_spec(frame, selector_mask)

    assert spec.feature == "trend_abs_1440_bps"
    assert spec.segment == "base"
    assert spec.operator == ">="
    assert spec.quantile == 0.80
    assert round(spec.threshold, 6) == 660.0
    assert spec.modifier == 1.10


def test_v159_overlay_boosts_only_base_high_trend_abs() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        {
            "v158_account_return_pct": [10.0, -10.0, 8.0, 6.0],
            "v158_account_pnl_bps": [100.0, -100.0, 80.0, 60.0],
            "leg": ["base", "base", "rescue", "base"],
            "side": ["long", "short", "long", "long"],
            "trend_abs_1440_bps": [700.0, 500.0, 900.0, 660.0],
        }
    )
    spec = module.BaseTrendAbsSpec(
        name="test",
        feature="trend_abs_1440_bps",
        segment="base",
        operator=">=",
        quantile=0.80,
        threshold=660.0,
        modifier=1.10,
    )

    out = module._apply_overlay(frame, spec)

    assert list(out["v159_base_trend_abs_boost_flag"]) == [True, False, False, True]
    assert list(out["v159_modifier"]) == [1.10, 1.0, 1.0, 1.10]
    assert list(out["v159_account_return_pct"].round(6)) == [11.0, -10.0, 8.0, 6.6]
    assert list(out["v159_account_pnl_bps"].round(6)) == [110.0, -100.0, 80.0, 66.0]


def test_v159_gate_requires_two_percent_incremental_improvement() -> None:
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
        "changed_selector_count": 80,
        "changed_holdout_count": 20,
        "full_return_pct": 101.9,
        "full_max_drawdown_pct": -10.0,
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

    assert module._passes_v159_gate(candidate, baseline) is False

    candidate["full_return_pct"] = 102.0

    assert module._passes_v159_gate(candidate, baseline) is True

    candidate["full_max_drawdown_pct"] = -10.1

    assert module._passes_v159_gate(candidate, baseline) is False
