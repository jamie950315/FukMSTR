from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v148_premium_basis_sentiment_overlay.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v148_premium_basis_sentiment_overlay", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v148_parse_premium_klines_uses_close_availability_time() -> None:
    module = _load_module()
    rows = [
        [1719792000000, "0.0001", "0.0002", "0.0000", "0.00015", "0", 1719795599999, "0", 1, "0", "0", "0"],
        [1719795600000, "0.0002", "0.0003", "0.0001", "0.00025", "0", 1719799199999, "0", 1, "0", "0", "0"],
    ]

    frame = module._parse_premium_klines(rows)

    assert list(frame["premium_close"]) == [0.00015, 0.00025]
    assert frame.loc[0, "premium_time"] == pd.Timestamp("2024-07-01T01:00:00Z")
    assert str(frame["premium_time"].dtype) == "datetime64[ns, UTC]"


def test_v148_join_uses_latest_closed_premium_not_current_hour_close() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        [
            {"timestamp": "2024-07-01T01:30:00Z", "signal": 1},
            {"timestamp": "2024-07-01T02:00:00Z", "signal": -1},
        ]
    )
    premium = pd.DataFrame(
        [
            {"premium_time": "2024-07-01T01:00:00Z", "premium_close": 0.0001},
            {"premium_time": "2024-07-01T02:00:00Z", "premium_close": 0.0005},
        ]
    )

    joined = module._join_prior_premium(trades, module._add_premium_features(premium))

    assert joined.loc[0, "premium_close"] == 0.0001
    assert joined.loc[1, "premium_close"] == 0.0005


def test_v148_premium_crowd_follow_is_direction_aware() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        [
            {"signal": 1, "premium_z_30d": 2.0, "premium_close_bps": 1.5},
            {"signal": -1, "premium_z_30d": -3.0, "premium_close_bps": -2.5},
            {"signal": 1, "premium_z_30d": -1.0, "premium_close_bps": -0.5},
        ]
    )

    enriched = module._add_signed_premium_sentiment_features(frame)

    assert enriched.loc[0, "premium_crowd_follow_30d"] == 2.0
    assert enriched.loc[1, "premium_crowd_follow_30d"] == 3.0
    assert enriched.loc[2, "premium_crowd_follow_30d"] == -1.0
    assert enriched.loc[1, "premium_crowd_follow_bps"] == 2.5


def test_v148_gate_rejects_return_gain_with_holdout_drawdown_degradation() -> None:
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
        "full_return_pct": 105.0,
        "full_max_drawdown_pct": -10.0,
        "full_positive_months": 3,
        "full_month_count": 3,
        "holdout_return_pct": 40.0,
        "holdout_max_drawdown_pct": -9.0,
        "holdout_positive_months": 1,
        "holdout_month_count": 1,
    }

    assert module._passes_v148_gate(candidate, baseline) is False

    candidate["holdout_max_drawdown_pct"] = -8.0

    assert module._passes_v148_gate(candidate, baseline) is True
