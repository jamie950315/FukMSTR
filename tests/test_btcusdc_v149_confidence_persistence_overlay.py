from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v149_confidence_persistence_overlay.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v149_confidence_persistence_overlay", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v149_candidate_specs_use_selector_quantiles_only() -> None:
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
            "prob_z_120d": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 999.0],
        }
    )
    selector_mask = frame["timestamp"] < pd.Timestamp("2026-01-01T00:00:00Z")

    specs = module._candidate_specs(frame, selector_mask)
    target = next(spec for spec in specs if spec.feature == "prob_z_120d" and spec.quantile == 0.75)

    assert target.threshold == 5.25


def test_v149_overlay_boosts_only_matching_confidence_zone() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        {
            "v148_account_return_pct": [10.0, -5.0, 8.0],
            "v148_account_pnl_bps": [100.0, -50.0, 80.0],
            "prob_z_120d": [2.6, 1.2, 3.0],
        }
    )
    spec = module.ConfidenceOverlaySpec(
        name="test",
        feature="prob_z_120d",
        operator=">=",
        quantile=0.67,
        threshold=2.5,
        multiplier=1.15,
    )

    out = module._apply_overlay(frame, spec)

    assert list(out["v149_multiplier"]) == [1.15, 1.0, 1.15]
    assert list(out["v149_account_return_pct"]) == [11.5, -5.0, 9.2]
    assert list(out["v149_account_pnl_bps"].round(6)) == [115.0, -50.0, 92.0]


def test_v149_selection_ignores_candidate_with_holdout_only_gain() -> None:
    module = _load_module()
    candidates = pd.DataFrame(
        [
            {
                "candidate": "selector_good",
                "selector_trade_count": 100,
                "changed_selector_count": 40,
                "selector_delta_return_pct": 5.0,
                "selector_delta_drawdown_pct": 0.0,
                "selector_positive_months": 2,
                "selector_month_count": 2,
                "changed_trade_count": 40,
            },
            {
                "candidate": "holdout_only",
                "selector_trade_count": 100,
                "changed_selector_count": 40,
                "selector_delta_return_pct": -1.0,
                "selector_delta_drawdown_pct": 0.0,
                "selector_positive_months": 2,
                "selector_month_count": 2,
                "changed_trade_count": 40,
            },
        ]
    )

    selected = module._select_best_candidate(candidates)

    assert selected["candidate"] == "selector_good"


def test_v149_gate_rejects_holdout_drawdown_degradation() -> None:
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
        "full_return_pct": 105.0,
        "full_max_drawdown_pct": -10.0,
        "full_positive_months": 3,
        "full_month_count": 3,
        "holdout_return_pct": 45.0,
        "holdout_max_drawdown_pct": -9.0,
        "holdout_positive_months": 1,
        "holdout_month_count": 1,
    }

    assert module._passes_v149_gate(candidate, baseline) is False

    candidate["holdout_max_drawdown_pct"] = -8.0

    assert module._passes_v149_gate(candidate, baseline) is True
