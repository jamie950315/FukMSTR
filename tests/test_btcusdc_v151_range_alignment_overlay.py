from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v151_range_alignment_overlay.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v151_range_alignment_overlay", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v151_candidate_specs_use_selector_quantiles_only() -> None:
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
            "range_align_1440": [-4.0, -3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 999.0],
        }
    )
    selector_mask = frame["timestamp"] < pd.Timestamp("2026-01-01T00:00:00Z")

    specs = module._candidate_specs(frame, selector_mask)
    target = next(
        spec
        for spec in specs
        if spec.feature == "range_align_1440" and spec.quantile == 0.67 and spec.multiplier == 1.15
    )

    assert round(target.threshold, 6) == 0.69


def test_v151_overlay_boosts_only_matching_range_alignment_zone() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        {
            "v150_account_return_pct": [10.0, -5.0, 8.0],
            "v150_account_pnl_bps": [100.0, -50.0, 80.0],
            "range_align_1440": [-0.5, -0.8, 0.1],
        }
    )
    spec = module.RangeAlignmentSpec(
        name="test",
        feature="range_align_1440",
        operator=">=",
        quantile=0.67,
        threshold=-0.636,
        multiplier=1.15,
    )

    out = module._apply_overlay(frame, spec)

    assert list(out["v151_multiplier"]) == [1.15, 1.0, 1.15]
    assert list(out["v151_account_return_pct"]) == [11.5, -5.0, 9.2]
    assert list(out["v151_account_pnl_bps"].round(6)) == [115.0, -50.0, 92.0]


def test_v151_selection_uses_selector_period_not_holdout() -> None:
    module = _load_module()
    candidates = pd.DataFrame(
        [
            {
                "candidate": "selector_good",
                "selector_trade_count": 100,
                "changed_selector_count": 40,
                "changed_trade_count": 50,
                "selector_delta_return_pct": 5.0,
                "selector_delta_drawdown_pct": 0.0,
                "selector_positive_months": 2,
                "selector_month_count": 2,
            },
            {
                "candidate": "holdout_only",
                "selector_trade_count": 100,
                "changed_selector_count": 40,
                "changed_trade_count": 50,
                "selector_delta_return_pct": -1.0,
                "selector_delta_drawdown_pct": 0.0,
                "selector_positive_months": 2,
                "selector_month_count": 2,
            },
        ]
    )

    selected = module._select_best_candidate(candidates)

    assert selected["candidate"] == "selector_good"


def test_v151_gate_rejects_small_holdout_support() -> None:
    module = _load_module()
    baseline = {
        "full": {
            "total_account_return_pct": 100.0,
            "max_drawdown_pct": -10.0,
            "positive_months": 3,
            "month_count": 3,
        },
        "holdout": {
            "total_account_return_pct": 40.0,
            "max_drawdown_pct": -8.0,
            "positive_months": 1,
            "month_count": 1,
        },
    }
    candidate = {
        "changed_holdout_count": 5,
        "full_return_pct": 105.0,
        "full_max_drawdown_pct": -10.0,
        "full_positive_months": 3,
        "full_month_count": 3,
        "holdout_return_pct": 45.0,
        "holdout_max_drawdown_pct": -8.0,
        "holdout_positive_months": 1,
        "holdout_month_count": 1,
    }

    assert module._passes_v151_gate(candidate, baseline) is False

    candidate["changed_holdout_count"] = 20

    assert module._passes_v151_gate(candidate, baseline) is True
