from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v156_base_long_premium_stepup.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v156_base_long_premium_stepup", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v156_stepup_uses_existing_v155_flag() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        {
            "v155_account_return_pct": [10.75, -5.375, 6.0],
            "v155_account_pnl_bps": [107.5, -53.75, 60.0],
            "v155_base_long_premium_flag": [True, True, False],
        }
    )

    out = module._apply_stepup(frame)

    assert list(out["v156_base_long_premium_stepup_flag"]) == [True, True, False]
    assert list(out["v156_modifier"].round(6)) == [
        round(1.10 / 1.075, 6),
        round(1.10 / 1.075, 6),
        1.0,
    ]
    assert list(out["v156_account_return_pct"].round(6)) == [11.0, -5.5, 6.0]
    assert list(out["v156_account_pnl_bps"].round(6)) == [110.0, -55.0, 60.0]


def test_v156_gate_requires_incremental_improvement_without_worse_drawdown() -> None:
    module = _load_module()
    baseline = {
        "full": {
            "total_account_return_pct": 100.0,
            "max_drawdown_pct": -10.0,
            "positive_months": 3,
            "month_count": 3,
        },
        "selector": {
            "total_account_return_pct": 80.0,
            "max_drawdown_pct": -9.0,
            "positive_months": 2,
            "month_count": 2,
        },
        "holdout": {
            "total_account_return_pct": 20.0,
            "max_drawdown_pct": -8.0,
            "positive_months": 1,
            "month_count": 1,
        },
    }
    candidate = {
        "changed_selector_count": 80,
        "changed_holdout_count": 20,
        "full_return_pct": 100.5,
        "full_max_drawdown_pct": -10.0,
        "full_positive_months": 3,
        "full_month_count": 3,
        "selector_return_pct": 81.0,
        "selector_max_drawdown_pct": -9.0,
        "selector_positive_months": 2,
        "selector_month_count": 2,
        "holdout_return_pct": 21.0,
        "holdout_max_drawdown_pct": -8.0,
        "holdout_positive_months": 1,
        "holdout_month_count": 1,
    }

    assert module._passes_v156_gate(candidate, baseline) is False

    candidate["full_return_pct"] = 101.0

    assert module._passes_v156_gate(candidate, baseline) is True

    candidate["selector_max_drawdown_pct"] = -9.1

    assert module._passes_v156_gate(candidate, baseline) is False
