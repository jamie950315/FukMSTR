from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v168_execution_readiness_gate.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v168_execution_readiness_gate", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v168_classifies_execution_modes_from_required_maker_share() -> None:
    module = _load_module()
    budget = pd.DataFrame(
        {
            "month": ["a", "b", "c", "d", "e"],
            "required_maker_share": [0.93, 0.70, 0.30, 0.0, 1.0],
            "max_taker_share": [0.07, 0.30, 0.70, 1.0, 0.0],
            "execution_budget_tag": ["maker_required", "maker_required", "maker_required", "taker_ok", "no_cost_headroom"],
        }
    )

    out = module._readiness_gate(budget)

    assert list(out["execution_readiness_mode"]) == [
        "maker_only_required",
        "maker_priority_required",
        "mixed_execution_allowed",
        "taker_allowed",
        "no_trade_unless_cost_improves",
    ]
    assert list(out["live_gate_action"]) == [
        "block_taker_execution",
        "prefer_maker_or_skip",
        "cap_taker_share",
        "normal_cost_monitoring",
        "skip_until_edge_or_cost_improves",
    ]


def test_v168_decision_blocks_live_promotion_when_maker_only_months_exist() -> None:
    module = _load_module()
    gate = pd.DataFrame(
        {
            "execution_readiness_mode": [
                "maker_only_required",
                "maker_priority_required",
                "taker_allowed",
            ],
            "required_maker_share": [0.93, 0.70, 0.0],
        }
    )

    decision = module._decision(gate)

    assert decision["status"] == "execution_readiness_warning"
    assert decision["promote_to_live"] is False
    assert decision["maker_only_required_month_count"] == 1
    assert decision["strictest_required_maker_share"] == 0.93


def test_v168_payload_declares_no_trade_or_threshold_changes() -> None:
    module = _load_module()
    payload = module._payload_for_gate(
        pd.DataFrame(
            {
                "execution_readiness_mode": ["taker_allowed"],
                "required_maker_share": [0.0],
            }
        )
    )

    assert payload["config"]["adds_new_trades"] is False
    assert payload["config"]["changes_existing_threshold"] is False
    assert payload["config"]["promotes_live_trading"] is False
