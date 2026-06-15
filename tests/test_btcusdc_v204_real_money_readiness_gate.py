from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v204_real_money_readiness_gate.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v204_real_money_readiness_gate", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v204_blocks_real_money_when_overfit_or_forward_evidence_fails() -> None:
    module = _load_module()

    payload = module._payload_for_readiness(
        overfit_payload={
            "decision": {
                "status": "post_goal_overfitting_warning",
                "stop_historical_optimization": True,
            }
        },
        forward_payload={
            "decision": {
                "status": "no_forward_evidence",
                "forward_evidence_available": False,
                "forward_trade_count": 0,
            }
        },
        realtime_summary={
            "rejected_signals": 0,
            "market_data_errors": 0,
        },
        execution_payload={
            "decision": {
                "status": "execution_validation_passed",
                "kill_switch_tested": True,
                "secrets_present_in_repo": False,
                "max_slippage_bps_p95": 2.0,
            }
        },
    )

    assert payload["decision"]["status"] == "real_money_blocked"
    assert payload["decision"]["promote_to_real_money"] is False
    assert "historical_optimization_frozen_clean" in payload["decision"]["failed_checks"]
    assert "forward_evidence_available" in payload["decision"]["failed_checks"]


def test_v204_requires_execution_validation_even_when_research_checks_pass() -> None:
    module = _load_module()

    payload = module._payload_for_readiness(
        overfit_payload={
            "decision": {
                "status": "post_goal_overfitting_not_detected",
                "stop_historical_optimization": False,
            }
        },
        forward_payload={
            "decision": {
                "status": "forward_evidence_available",
                "forward_evidence_available": True,
                "forward_trade_count": 30,
            }
        },
        realtime_summary={
            "rejected_signals": 0,
            "market_data_errors": 0,
        },
        execution_payload=None,
    )

    assert payload["decision"]["promote_to_real_money"] is False
    assert "execution_validation_passed" in payload["decision"]["failed_checks"]


def test_v204_passes_only_when_all_real_money_gates_are_clean() -> None:
    module = _load_module()

    payload = module._payload_for_readiness(
        overfit_payload={
            "decision": {
                "status": "post_goal_overfitting_not_detected",
                "stop_historical_optimization": False,
            }
        },
        forward_payload={
            "decision": {
                "status": "forward_evidence_available",
                "forward_evidence_available": True,
                "forward_trade_count": 30,
            }
        },
        realtime_summary={
            "rejected_signals": 0,
            "market_data_errors": 0,
        },
        execution_payload={
            "decision": {
                "status": "execution_validation_passed",
                "kill_switch_tested": True,
                "secrets_present_in_repo": False,
                "max_slippage_bps_p95": 2.0,
            }
        },
    )

    assert payload["decision"]["status"] == "real_money_ready"
    assert payload["decision"]["promote_to_real_money"] is True
    assert payload["decision"]["failed_checks"] == []
