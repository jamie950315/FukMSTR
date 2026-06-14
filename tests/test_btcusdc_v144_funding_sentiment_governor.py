from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v144_funding_sentiment_governor.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v144_funding_sentiment_governor", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v144_join_uses_latest_prior_funding_not_future_value() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        [
            {"timestamp": "2026-01-01T10:00:00Z", "signal": 1, "account_return_pct": 1.0},
            {"timestamp": "2026-01-01T15:00:00Z", "signal": -1, "account_return_pct": -0.5},
        ]
    )
    funding = pd.DataFrame(
        [
            {"funding_time": "2026-01-01T08:00:00Z", "funding_rate": 0.0001},
            {"funding_time": "2026-01-01T16:00:00Z", "funding_rate": -0.0002},
        ]
    )

    joined = module._join_prior_funding(trades, module._add_funding_history_features(funding))

    assert joined.loc[0, "funding_rate"] == 0.0001
    assert joined.loc[1, "funding_rate"] == 0.0001
    assert joined.loc[1, "funding_time"] == pd.Timestamp("2026-01-01T08:00:00Z")


def test_v144_join_normalizes_mixed_datetime_precision_from_api_downloads() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        [
            {"timestamp": pd.Timestamp("2026-01-01T10:00:00Z").as_unit("us"), "signal": 1},
        ]
    )
    funding = pd.DataFrame(
        [
            {"funding_time": pd.Timestamp("2026-01-01T08:00:00Z").as_unit("ms"), "funding_rate": 0.0001},
        ]
    )

    joined = module._join_prior_funding(trades, module._add_funding_history_features(funding))

    assert joined.loc[0, "funding_rate"] == 0.0001


def test_v144_to_utc_accepts_cached_mixed_timestamp_strings() -> None:
    module = _load_module()
    series = pd.Series(["2024-07-07 00:00:00+00:00", "2024-07-07 08:00:00.001000+00:00"])

    parsed = module._to_utc(series)

    assert str(parsed.dtype) == "datetime64[ns, UTC]"
    assert parsed.iloc[1] == pd.Timestamp("2024-07-07T08:00:00.001000Z")


def test_v144_funding_crowd_follow_is_signed_by_trade_direction() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        [
            {"signal": 1, "funding_z_30d": 2.0, "funding_rate_bps": 1.5},
            {"signal": -1, "funding_z_30d": -3.0, "funding_rate_bps": -2.5},
            {"signal": 1, "funding_z_30d": -1.0, "funding_rate_bps": -0.5},
        ]
    )

    enriched = module._add_signed_funding_sentiment_features(frame)

    assert enriched.loc[0, "funding_crowd_follow_30d"] == 2.0
    assert enriched.loc[1, "funding_crowd_follow_30d"] == 3.0
    assert enriched.loc[2, "funding_crowd_follow_30d"] == -1.0
    assert enriched.loc[0, "funding_crowd_follow_bps"] == 1.5
    assert enriched.loc[1, "funding_crowd_follow_bps"] == 2.5


def test_v144_gate_rejects_return_gain_with_worse_drawdown_or_lost_months() -> None:
    module = _load_module()
    baseline = {
        "full": {
            "total_account_return_pct": 100.0,
            "max_drawdown_pct": -10.0,
            "positive_months": 3,
            "month_count": 3,
        },
        "holdout": {
            "total_account_return_pct": 20.0,
            "max_drawdown_pct": -4.0,
            "positive_months": 1,
            "month_count": 1,
        },
    }
    candidate = {
        "full_return_pct": 120.0,
        "full_max_drawdown_pct": -12.0,
        "full_positive_months": 2,
        "full_month_count": 3,
        "holdout_return_pct": 25.0,
        "holdout_max_drawdown_pct": -4.0,
        "holdout_positive_months": 1,
        "holdout_month_count": 1,
    }

    assert module._passes_v144_gate(candidate, baseline) is False

    candidate["full_max_drawdown_pct"] = -10.0
    candidate["full_positive_months"] = 3

    assert module._passes_v144_gate(candidate, baseline) is True
