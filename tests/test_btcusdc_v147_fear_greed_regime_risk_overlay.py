from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v147_fear_greed_regime_risk_overlay.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v147_fear_greed_regime_risk_overlay", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v147_labels_fear_greed_regime_buckets() -> None:
    module = _load_module()
    frame = pd.DataFrame({"fng_value": [10, 30, 50, 65, 90]})

    labelled = module._add_regime_features(frame)

    assert list(labelled["fng_regime"]) == ["extreme_fear", "fear", "neutral", "greed", "extreme_greed"]


def test_v147_apply_regime_overlay_only_changes_matching_bucket() -> None:
    module = _load_module()
    frame = module._add_regime_features(
        pd.DataFrame(
            [
                {"fng_value": 30, "fng_crowd_follow": 4.0, "candidate_account_return_pct": 10.0, "candidate_account_pnl_bps": 1000.0},
                {"fng_value": 80, "fng_crowd_follow": 4.0, "candidate_account_return_pct": 20.0, "candidate_account_pnl_bps": 2000.0},
            ]
        )
    )
    spec = module.RegimeRiskSpec(
        name="trim_fear",
        lower=25.0,
        upper=44.0,
        multiplier=0.5,
        crowd_operator="any",
        crowd_threshold=0.0,
    )

    adjusted = module._apply_regime_overlay(frame, spec)

    assert list(adjusted["v147_multiplier"]) == [0.5, 1.0]
    assert list(adjusted["v147_account_return_pct"]) == [5.0, 20.0]
    assert list(adjusted["v147_account_pnl_bps"]) == [500.0, 2000.0]


def test_v147_selector_chooses_without_holdout_gain() -> None:
    module = _load_module()
    candidates = pd.DataFrame(
        [
            {
                "candidate": "selector_best_but_holdout_bad",
                "selector_trade_count": 100,
                "selector_delta_return_pct": 10.0,
                "selector_delta_drawdown_pct": 0.0,
                "selector_positive_months": 3,
                "selector_month_count": 3,
                "holdout_delta_return_pct": -10.0,
            },
            {
                "candidate": "selector_weaker_but_holdout_good",
                "selector_trade_count": 100,
                "selector_delta_return_pct": 5.0,
                "selector_delta_drawdown_pct": 0.0,
                "selector_positive_months": 3,
                "selector_month_count": 3,
                "holdout_delta_return_pct": 20.0,
            },
        ]
    )

    selected = module._select_best_candidate(candidates)

    assert selected["candidate"] == "selector_best_but_holdout_bad"


def test_v147_gate_rejects_selector_gain_when_holdout_loses_return() -> None:
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
        "full_return_pct": 101.0,
        "full_max_drawdown_pct": -10.0,
        "full_positive_months": 3,
        "full_month_count": 3,
        "holdout_return_pct": 39.0,
        "holdout_max_drawdown_pct": -8.0,
        "holdout_positive_months": 1,
        "holdout_month_count": 1,
    }

    assert module._passes_v147_gate(candidate, baseline) is False

    candidate["holdout_return_pct"] = 41.0

    assert module._passes_v147_gate(candidate, baseline) is True
