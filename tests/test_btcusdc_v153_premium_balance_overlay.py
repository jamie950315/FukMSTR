from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v153_premium_balance_overlay.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v153_premium_balance_overlay", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v153_specs_use_selector_quantiles_by_segment() -> None:
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
            "premium_abs_bps": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 999.0],
            "premium_crowd_follow_120d": [-8.0, -7.0, -6.0, -5.0, -4.0, -3.0, -2.0, -1.0, -999.0],
        }
    )
    selector_mask = frame["timestamp"] < pd.Timestamp("2026-01-01T00:00:00Z")

    specs = module._overlay_specs(frame, selector_mask)

    assert round(specs["boost"].threshold, 6) == 2.4
    assert round(specs["throttle"].threshold, 6) == -7.3


def test_v153_overlay_boosts_calm_longs_and_throttles_stressed_base_longs() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        {
            "v152_account_return_pct": [10.0, -10.0, 8.0, 6.0],
            "v152_account_pnl_bps": [100.0, -100.0, 80.0, 60.0],
            "leg": ["rescue", "base", "base", "base"],
            "side": ["long", "long", "long", "short"],
            "premium_abs_bps": [1.0, 5.0, 1.0, 1.0],
            "premium_crowd_follow_120d": [0.0, -3.0, -3.0, -3.0],
        }
    )
    specs = {
        "boost": module.PremiumBalanceSpec(
            name="boost",
            feature="premium_abs_bps",
            segment="long",
            operator="<=",
            quantile=0.2,
            threshold=2.0,
            multiplier=1.15,
        ),
        "throttle": module.PremiumBalanceSpec(
            name="throttle",
            feature="premium_crowd_follow_120d",
            segment="base_long",
            operator="<=",
            quantile=0.1,
            threshold=-1.0,
            multiplier=0.70,
        ),
    }

    out = module._apply_overlay(frame, specs)

    assert list(out["v153_boost_flag"]) == [True, False, True, False]
    assert list(out["v153_throttle_flag"]) == [False, True, True, False]
    assert list(out["v153_multiplier"]) == [1.15, 0.70, 0.70, 1.0]
    assert list(out["v153_account_return_pct"]) == [11.5, -7.0, 5.6, 6.0]
    assert list(out["v153_account_pnl_bps"].round(6)) == [115.0, -70.0, 56.0, 60.0]


def test_v153_gate_requires_five_percent_full_improvement() -> None:
    module = _load_module()
    baseline = {
        "full": {
            "total_account_return_pct": 100.0,
            "max_drawdown_pct": -10.0,
            "positive_months": 3,
            "month_count": 3,
        },
        "selector": {
            "total_account_return_pct": 80.0,
            "max_drawdown_pct": -9.0,
            "positive_months": 2,
            "month_count": 2,
        },
        "holdout": {
            "total_account_return_pct": 20.0,
            "max_drawdown_pct": -8.0,
            "positive_months": 1,
            "month_count": 1,
        },
    }
    candidate = {
        "changed_selector_count": 80,
        "changed_holdout_count": 20,
        "full_return_pct": 104.0,
        "full_max_drawdown_pct": -10.0,
        "full_positive_months": 3,
        "full_month_count": 3,
        "selector_return_pct": 90.0,
        "selector_max_drawdown_pct": -9.0,
        "selector_positive_months": 2,
        "selector_month_count": 2,
        "holdout_return_pct": 22.0,
        "holdout_max_drawdown_pct": -8.0,
        "holdout_positive_months": 1,
        "holdout_month_count": 1,
    }

    assert module._passes_v153_gate(candidate, baseline) is False

    candidate["full_return_pct"] = 105.0

    assert module._passes_v153_gate(candidate, baseline) is True
