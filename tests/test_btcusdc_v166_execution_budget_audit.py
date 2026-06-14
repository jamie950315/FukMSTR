from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v166_execution_budget_audit.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v166_execution_budget_audit", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v166_execution_budget_caps_taker_share_from_breakeven_cost() -> None:
    module = _load_module()
    monthly = pd.DataFrame(
        {
            "month": ["a", "b", "c"],
            "breakeven_extra_cost_bps": [0.5, 4.0, 8.0],
        }
    )

    out = module._execution_budget(monthly, taker_extra_cost_bps=4.0)

    assert list(out["max_taker_share"].round(6)) == [0.125, 1.0, 1.0]
    assert list(out["required_maker_share"].round(6)) == [0.875, 0.0, 0.0]
    assert list(out["execution_budget_tag"]) == ["maker_required", "taker_ok", "taker_ok"]


def test_v166_execution_budget_handles_no_cost_headroom() -> None:
    module = _load_module()
    monthly = pd.DataFrame(
        {
            "month": ["a"],
            "breakeven_extra_cost_bps": [-0.1],
        }
    )

    out = module._execution_budget(monthly, taker_extra_cost_bps=4.0)

    assert out.iloc[0]["max_taker_share"] == 0.0
    assert out.iloc[0]["required_maker_share"] == 1.0
    assert out.iloc[0]["execution_budget_tag"] == "no_cost_headroom"


def test_v166_decision_warns_when_maker_required_months_exist() -> None:
    module = _load_module()
    budget = pd.DataFrame(
        {
            "max_taker_share": [1.0, 0.25],
            "execution_budget_tag": ["taker_ok", "maker_required"],
        }
    )

    decision = module._decision(budget, taker_extra_cost_bps=4.0)

    assert decision["status"] == "execution_budget_warning"
    assert decision["maker_required_month_count"] == 1
    assert decision["minimum_max_taker_share"] == 0.25
