from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v146_fear_greed_macro_overlay.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v146_fear_greed_macro_overlay", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v146_parse_fng_payload_sorts_old_to_new_and_normalizes_values() -> None:
    module = _load_module()
    payload = {
        "name": "Fear and Greed Index",
        "data": [
            {"value": "80", "value_classification": "Extreme Greed", "timestamp": "1719964800"},
            {"value": "20", "value_classification": "Extreme Fear", "timestamp": "1719878400"},
        ],
        "metadata": {"error": None},
    }

    frame = module._parse_fng_payload(payload)

    assert list(frame["fng_value"]) == [20, 80]
    assert str(frame["fng_time"].dtype) == "datetime64[ns, UTC]"
    assert list(frame["fng_classification"]) == ["Extreme Fear", "Extreme Greed"]


def test_v146_join_uses_latest_prior_daily_sentiment_not_future_day() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        [
            {"timestamp": "2024-07-02T01:00:00Z", "signal": 1},
            {"timestamp": "2024-07-02T23:59:00Z", "signal": -1},
        ]
    )
    fng = pd.DataFrame(
        [
            {"fng_time": "2024-07-02T00:00:00Z", "fng_value": 30, "fng_classification": "Fear"},
            {"fng_time": "2024-07-03T00:00:00Z", "fng_value": 90, "fng_classification": "Extreme Greed"},
        ]
    )

    joined = module._join_prior_fng(trades, fng)

    assert joined.loc[0, "fng_value"] == 30
    assert joined.loc[1, "fng_value"] == 30
    assert joined.loc[1, "fng_time"] == pd.Timestamp("2024-07-02T00:00:00Z")


def test_v146_fng_features_are_direction_aware() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        [
            {"signal": 1, "fng_value": 80},
            {"signal": -1, "fng_value": 20},
            {"signal": 1, "fng_value": 20},
            {"signal": -1, "fng_value": 80},
        ]
    )

    enriched = module._add_fng_macro_features(frame)

    assert enriched.loc[0, "fng_crowd_follow"] == 30
    assert enriched.loc[1, "fng_crowd_follow"] == 30
    assert enriched.loc[2, "fng_crowd_follow"] == -30
    assert enriched.loc[3, "fng_crowd_follow"] == -30
    assert enriched.loc[0, "fng_extreme_distance"] == 30


def test_v146_gate_rejects_holdout_drawdown_degradation_even_with_full_gain() -> None:
    module = _load_module()
    baseline = {
        "full": {
            "total_account_return_pct": 100.0,
            "max_drawdown_pct": -10.0,
            "positive_months": 3,
            "month_count": 3,
        },
        "holdout": {
            "total_account_return_pct": 30.0,
            "max_drawdown_pct": -8.0,
            "positive_months": 1,
            "month_count": 1,
        },
    }
    candidate = {
        "full_return_pct": 104.0,
        "full_max_drawdown_pct": -10.0,
        "full_positive_months": 3,
        "full_month_count": 3,
        "holdout_return_pct": 40.0,
        "holdout_max_drawdown_pct": -9.0,
        "holdout_positive_months": 1,
        "holdout_month_count": 1,
    }

    assert module._passes_v146_gate(candidate, baseline) is False

    candidate["holdout_max_drawdown_pct"] = -8.0

    assert module._passes_v146_gate(candidate, baseline) is True
