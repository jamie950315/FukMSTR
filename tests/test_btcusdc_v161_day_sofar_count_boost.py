from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v161_day_sofar_count_boost.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v161_day_sofar_count_boost", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v161_spec_uses_selector_all_day_sofar_count_quantile() -> None:
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
            "leg": ["base", "rescue", "base", "rescue", "base", "rescue", "base", "rescue", "base"],
            "side": ["long"] * 9,
            "day_sofar_count": [10, 20, 30, 40, 50, 60, 70, 80, 999],
        }
    )
    selector_mask = frame["timestamp"] < pd.Timestamp("2026-01-01T00:00:00Z")

    spec = module._overlay_spec(frame, selector_mask)

    assert spec.feature == "day_sofar_count"
    assert spec.segment == "all"
    assert spec.operator == "<="
    assert spec.quantile == 0.30
    assert round(spec.threshold, 6) == 31.0
    assert spec.modifier == 1.05


def test_v161_overlay_boosts_all_low_day_sofar_count_trades() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        {
            "v160_account_return_pct": [10.0, -10.0, 8.0, 6.0],
            "v160_account_pnl_bps": [100.0, -100.0, 80.0, 60.0],
            "leg": ["base", "rescue", "base", "rescue"],
            "side": ["long", "short", "short", "long"],
            "day_sofar_count": [10, 140, 141, 80],
        }
    )
    spec = module.DaySofarCountSpec(
        name="test",
        feature="day_sofar_count",
        segment="all",
        operator="<=",
        quantile=0.30,
        threshold=140.0,
        modifier=1.05,
    )

    out = module._apply_overlay(frame, spec)

    assert list(out["v161_day_sofar_count_boost_flag"]) == [True, True, False, True]
    assert list(out["v161_modifier"]) == [1.05, 1.05, 1.0, 1.05]
    assert list(out["v161_account_return_pct"].round(6)) == [10.5, -10.5, 8.0, 6.3]
    assert list(out["v161_account_pnl_bps"].round(6)) == [105.0, -105.0, 80.0, 63.0]


def test_v161_gate_requires_incremental_improvement_without_worse_risk() -> None:
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
        "full_return_pct": 100.9,
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

    assert module._passes_v161_gate(candidate, baseline) is False

    candidate["full_return_pct"] = 101.0

    assert module._passes_v161_gate(candidate, baseline) is True

    candidate["holdout_max_drawdown_pct"] = -8.1

    assert module._passes_v161_gate(candidate, baseline) is False
