from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v155_base_long_premium_expansion.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v155_base_long_premium_expansion", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v155_spec_uses_selector_base_long_quantile() -> None:
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
        }
    )
    selector_mask = frame["timestamp"] < pd.Timestamp("2026-01-01T00:00:00Z")

    spec = module._overlay_spec(frame, selector_mask)

    assert spec.segment == "base_long"
    assert spec.feature == "premium_abs_bps"
    assert spec.operator == "<="
    assert spec.quantile == 0.60
    assert round(spec.threshold, 6) == 5.2
    assert spec.modifier == 1.075


def test_v155_overlay_expands_only_base_long_calm_premium() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        {
            "v154_account_return_pct": [10.0, -10.0, 8.0, 6.0],
            "v154_account_pnl_bps": [100.0, -100.0, 80.0, 60.0],
            "leg": ["base", "base", "rescue", "base"],
            "side": ["long", "short", "long", "long"],
            "premium_abs_bps": [2.0, 2.0, 2.0, 8.0],
        }
    )
    spec = module.BaseLongPremiumSpec(
        name="test",
        feature="premium_abs_bps",
        segment="base_long",
        operator="<=",
        quantile=0.60,
        threshold=5.0,
        modifier=1.075,
    )

    out = module._apply_overlay(frame, spec)

    assert list(out["v155_base_long_premium_flag"]) == [True, False, False, False]
    assert list(out["v155_modifier"]) == [1.075, 1.0, 1.0, 1.0]
    assert list(out["v155_account_return_pct"].round(6)) == [10.75, -10.0, 8.0, 6.0]
    assert list(out["v155_account_pnl_bps"].round(6)) == [107.5, -100.0, 80.0, 60.0]


def test_v155_gate_requires_three_percent_full_improvement() -> None:
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
        "full_return_pct": 102.0,
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

    assert module._passes_v155_gate(candidate, baseline) is False

    candidate["full_return_pct"] = 103.0

    assert module._passes_v155_gate(candidate, baseline) is True
