from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v165_cost_fragility_audit.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v165_cost_fragility_audit", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v165_monthly_cost_fragility_computes_breakeven_and_stressed_returns() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00:00Z",
                    "2026-01-02T00:00:00Z",
                    "2026-02-01T00:00:00Z",
                ],
                utc=True,
            ),
            "v162_account_return_pct": [1.0, 2.0, 10.0],
            "account_leverage": [3.0, 2.0, 5.0],
            "position_weight": [1.0, 0.5, 2.0],
            "leg": ["base", "rescue", "base"],
            "side": ["long", "short", "long"],
        }
    )

    out = module._monthly_cost_fragility(frame, extra_cost_bps_values=(2.0, 4.0))

    jan = out.loc[out["month"].eq("2026-01")].iloc[0]
    feb = out.loc[out["month"].eq("2026-02")].iloc[0]

    assert jan["trade_count"] == 2
    assert round(jan["base_return_pct"], 6) == 3.0
    assert round(jan["cost_load_per_1bps_pct"], 6) == 0.04
    assert round(jan["breakeven_extra_cost_bps"], 6) == 75.0
    assert round(jan["return_after_2bps_pct"], 6) == 2.92
    assert round(jan["return_after_4bps_pct"], 6) == 2.84
    assert feb["trade_count"] == 1
    assert round(feb["cost_load_per_1bps_pct"], 6) == 0.10


def test_v165_fragility_tags_months_below_required_cost_headroom() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        {
            "month": ["a", "b", "c"],
            "breakeven_extra_cost_bps": [0.5, 2.0, 10.0],
        }
    )

    out = module._tag_fragility(frame, required_extra_cost_bps=4.0)

    assert list(out["cost_fragility_tag"]) == ["critical", "thin", "ok"]
    assert list(out["passes_required_cost_headroom"]) == [False, False, True]


def test_v165_decision_warns_when_any_month_fails_required_headroom() -> None:
    module = _load_module()
    monthly = pd.DataFrame(
        {
            "passes_required_cost_headroom": [True, False],
            "breakeven_extra_cost_bps": [5.0, 1.0],
        }
    )

    decision = module._decision(monthly, required_extra_cost_bps=4.0)

    assert decision["status"] == "cost_fragility_warning"
    assert decision["fragile_month_count"] == 1
    assert decision["minimum_breakeven_extra_cost_bps"] == 1.0
