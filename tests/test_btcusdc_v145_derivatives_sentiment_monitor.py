from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v145_derivatives_sentiment_monitor.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v145_derivatives_sentiment_monitor", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v145_metric_join_uses_latest_prior_row_not_future_value() -> None:
    module = _load_module()
    trades = pd.DataFrame(
        [
            {"timestamp": "2026-06-01T10:00:00Z", "signal": 1},
            {"timestamp": "2026-06-01T11:30:00Z", "signal": -1},
        ]
    )
    metric = pd.DataFrame(
        [
            {"metric_time": "2026-06-01T09:00:00Z", "long_short_ratio": 1.2},
            {"metric_time": "2026-06-01T12:00:00Z", "long_short_ratio": 0.8},
        ]
    )

    joined = module._join_prior_metric(
        trades,
        metric,
        metric_time_col="metric_time",
        metric_cols=["long_short_ratio"],
    )

    assert joined.loc[0, "long_short_ratio"] == 1.2
    assert joined.loc[1, "long_short_ratio"] == 1.2
    assert joined.loc[1, "metric_time"] == pd.Timestamp("2026-06-01T09:00:00Z")


def test_v145_derivatives_features_are_direction_aware() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        [
            {
                "signal": 1,
                "sum_open_interest_value": 100.0,
                "global_long_short_ratio": 1.5,
                "top_position_long_short_ratio": 1.4,
            },
            {
                "signal": -1,
                "sum_open_interest_value": 130.0,
                "global_long_short_ratio": 0.7,
                "top_position_long_short_ratio": 0.6,
            },
            {
                "signal": 1,
                "sum_open_interest_value": 110.0,
                "global_long_short_ratio": 0.8,
                "top_position_long_short_ratio": 0.9,
            },
        ]
    )

    enriched = module._add_derivatives_sentiment_features(frame)

    assert enriched.loc[0, "global_crowd_follow"] > 0.0
    assert enriched.loc[1, "global_crowd_follow"] > 0.0
    assert enriched.loc[2, "global_crowd_follow"] < 0.0
    assert enriched.loc[1, "oi_value_change_pct"] == 30.0
    assert enriched.loc[2, "oi_value_change_pct"] < 0.0


def test_v145_coverage_policy_keeps_recent_only_data_out_of_strategy_promotion() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-06-01T00:00:00Z", "2026-06-20T00:00:00Z"], utc=True),
            "global_long_short_ratio": [1.1, 1.2],
            "sum_open_interest_value": [100.0, 110.0],
        }
    )

    coverage = module._sentiment_coverage_summary(frame)

    assert coverage["coverage_policy"] == "recent_monitoring_only"
    assert coverage["eligible_for_strategy_promotion"] is False


def test_v145_labels_crowded_long_and_crowded_short_risk_zones() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        [
            {
                "timestamp": "2026-06-01T00:00:00Z",
                "signal": 1,
                "global_crowd_follow": 0.8,
                "top_position_crowd_follow": 0.7,
                "oi_value_change_pct": 3.0,
            },
            {
                "timestamp": "2026-06-01T01:00:00Z",
                "signal": -1,
                "global_crowd_follow": 0.9,
                "top_position_crowd_follow": 0.8,
                "oi_value_change_pct": 2.5,
            },
            {
                "timestamp": "2026-06-01T02:00:00Z",
                "signal": 1,
                "global_crowd_follow": -0.3,
                "top_position_crowd_follow": -0.1,
                "oi_value_change_pct": -1.0,
            },
        ]
    )

    labelled = module._label_recent_derivatives_context(frame)

    assert labelled.loc[0, "derivatives_context"] == "crowded_long_risk"
    assert labelled.loc[1, "derivatives_context"] == "crowded_short_risk"
    assert labelled.loc[2, "derivatives_context"] == "not_crowded_or_deleveraging"
