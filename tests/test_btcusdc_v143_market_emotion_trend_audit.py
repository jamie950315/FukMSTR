from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v143_market_emotion_trend_audit.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v143_market_emotion_trend_audit", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v143_joins_v142_with_prior_only_trend_and_emotion_features() -> None:
    module = _load_module()
    v142 = pd.DataFrame(
        [
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "month": "2026-01",
                "signal": pd.NA,
                "account_pnl_bps": 100.0,
                "account_return_pct": 1.0,
            }
        ]
    )
    feature_frame = pd.DataFrame(
        [
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "signal": -1,
                "prior_ret_30_bps": 12.5,
                "prior_range_pos_30": 0.8,
                "prior_ret_720_bps": -40.0,
                "prior_range_pos_720": 0.2,
                "prob_z_30d": 1.7,
                "prob_vs_day_sofar_max": 0.95,
            }
        ]
    )

    joined = module._join_v142_with_v119_features(v142, feature_frame)
    enriched = module._add_market_emotion_trend_features(joined)

    assert enriched.loc[0, "signal"] == -1
    assert enriched.loc[0, "side"] == "short"
    assert enriched.loc[0, "trend_follow_30_bps"] == -12.5
    assert enriched.loc[0, "trend_follow_720_bps"] == 40.0
    assert round(float(enriched.loc[0, "range_align_30"]), 6) == -0.6
    assert round(float(enriched.loc[0, "range_align_720"]), 6) == 0.6
    assert enriched.loc[0, "emotion_prob_z_30d"] == 1.7
    assert enriched.loc[0, "emotion_day_peak"] == 0.95


def test_v143_metrics_keep_zero_trade_months_when_filter_removes_a_month() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        [
            {"timestamp": "2026-01-01T00:00:00Z", "account_pnl_bps": 100.0, "account_return_pct": 1.0},
            {"timestamp": "2026-02-01T00:00:00Z", "account_pnl_bps": -50.0, "account_return_pct": -0.5},
        ]
    )
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    baseline_months = pd.Index(["2026-01", "2026-02"], name="month")

    metrics = module._account_metrics(
        "filtered",
        frame.iloc[:1].copy(),
        return_col="account_return_pct",
        pnl_col="account_pnl_bps",
        baseline_months=baseline_months,
    )

    assert metrics["trade_count"] == 1
    assert metrics["month_count"] == 2
    assert metrics["positive_months"] == 1
    assert metrics["worst_month_pct"] == 0.0


def test_v143_candidate_selection_is_based_on_selector_not_holdout() -> None:
    module = _load_module()
    candidates = pd.DataFrame(
        [
            {
                "candidate": "selector_good_holdout_bad",
                "policy_type": "sizing",
                "feature": "trend_follow_30_bps",
                "operator": "<=",
                "threshold": 0.0,
                "selector_delta_return_pct": 10.0,
                "selector_delta_drawdown_pct": 1.0,
                "selector_positive_months": 2,
                "selector_month_count": 2,
                "holdout_delta_return_pct": -20.0,
                "holdout_delta_drawdown_pct": -5.0,
                "full_delta_return_pct": -10.0,
            },
            {
                "candidate": "selector_weaker_holdout_good",
                "policy_type": "sizing",
                "feature": "trend_follow_720_bps",
                "operator": ">=",
                "threshold": 1.0,
                "selector_delta_return_pct": 4.0,
                "selector_delta_drawdown_pct": 0.5,
                "selector_positive_months": 2,
                "selector_month_count": 2,
                "holdout_delta_return_pct": 30.0,
                "holdout_delta_drawdown_pct": 2.0,
                "full_delta_return_pct": 34.0,
            },
        ]
    )

    selected = module._select_best_candidate(candidates)

    assert selected["candidate"] == "selector_good_holdout_bad"
