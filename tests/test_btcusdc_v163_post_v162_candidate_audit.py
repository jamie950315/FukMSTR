from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v163_post_v162_candidate_audit.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v163_post_v162_candidate_audit", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v163_feature_filter_excludes_post_trade_and_used_family_columns() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        {
            "v162_account_return_pct": [1.0, 2.0, 3.0, 4.0],
            "v162_account_pnl_bps": [10.0, 20.0, 30.0, 40.0],
            "drawdown_pct": [0.0, -1.0, -2.0, -3.0],
            "day_sofar_count": [1, 2, 3, 4],
            "trend_follow_1440_bps": [10.0, 20.0, 30.0, 40.0],
            "prior_ret_1440_bps": [10.0, 20.0, 30.0, 40.0],
            "premium_abs_bps": [0.1, 0.2, 0.3, 0.4],
            "funding_z_120d": [-1.0, 0.0, 1.0, 2.0],
            "side": ["long", "short", "long", "short"],
        }
    )

    features = module._candidate_feature_columns(frame, min_non_null=4, min_unique=4)

    assert "premium_abs_bps" in features
    assert "funding_z_120d" in features
    assert "v162_account_return_pct" not in features
    assert "v162_account_pnl_bps" not in features
    assert "drawdown_pct" not in features
    assert "day_sofar_count" not in features
    assert "trend_follow_1440_bps" not in features
    assert "prior_ret_1440_bps" not in features
    assert "side" not in features


def test_v163_gate_requires_return_improvement_and_no_worse_risk() -> None:
    module = _load_module()
    baseline = {
        "full": {"total_account_return_pct": 100.0, "max_drawdown_pct": -10.0, "worst_month_pct": 0.1},
        "selector": {"total_account_return_pct": 80.0, "max_drawdown_pct": -9.0, "worst_month_pct": 0.1},
        "holdout": {"total_account_return_pct": 20.0, "max_drawdown_pct": -8.0, "worst_month_pct": 0.1},
    }
    candidate = {
        "full_return_pct": 100.4,
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

    assert module._passes_promotion_gate(candidate, baseline) is False

    candidate["full_return_pct"] = 100.5

    assert module._passes_promotion_gate(candidate, baseline) is True

    candidate["selector_max_drawdown_pct"] = -9.1

    assert module._passes_promotion_gate(candidate, baseline) is False
