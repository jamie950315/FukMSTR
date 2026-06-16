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


def _public_data_payload() -> dict[str, object]:
    return {
        "decision": {
            "status": "public_data_availability_passed",
            "public_data_available": True,
            "failed_checks": [],
        }
    }


def _execution_payload() -> dict[str, object]:
    return {
        "checks": {
            "fill_evidence_available": True,
            "filled_status_clean": True,
            "execution_provenance_clean": True,
            "signal_provenance_clean": True,
            "slippage_p95_clean": True,
            "recent_execution_evidence_clean": True,
            "kill_switch_tested": True,
            "secrets_absent_from_repo": True,
        },
        "decision": {
            "status": "execution_validation_passed",
            "execution_validation_passed": True,
            "kill_switch_tested": True,
            "secrets_present_in_repo": False,
            "max_slippage_bps_p95": 2.0,
            "failed_checks": [],
        },
        "evidence": {
            "fill_count": 30,
            "latest_execution_timestamp": "2026-06-16T00:31:00+00:00",
            "execution_evidence_age_days": 1.0,
        },
    }


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
        execution_payload=_execution_payload(),
        forward_freshness_payload={
            "decision": {
                "status": "forward_fresh_no_signal",
                "forward_data_current": True,
                "forward_evidence_available": False,
            }
        },
        public_data_payload=_public_data_payload(),
        readiness_input_hashes={"test_input": "test_hash"},
    )

    assert payload["decision"]["status"] == "real_money_blocked"
    assert payload["decision"]["promote_to_real_money"] is False
    assert "historical_optimization_frozen_clean" in payload["decision"]["failed_checks"]
    assert "forward_evidence_available" in payload["decision"]["failed_checks"]
    assert "forward_freshness_clean" in payload["decision"]["failed_checks"]


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
        forward_freshness_payload={
            "decision": {
                "status": "forward_freshness_passed",
                "forward_data_current": True,
                "forward_evidence_available": True,
            }
        },
        public_data_payload=_public_data_payload(),
        readiness_input_hashes={"test_input": "test_hash"},
    )

    assert payload["decision"]["promote_to_real_money"] is False
    assert "execution_validation_passed" in payload["decision"]["failed_checks"]


def test_v204_blocks_legacy_execution_summary_without_provenance_checks() -> None:
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
                "failed_checks": [],
            }
        },
        forward_freshness_payload={
            "decision": {
                "status": "forward_freshness_passed",
                "forward_data_current": True,
                "forward_evidence_available": True,
            }
        },
        public_data_payload=_public_data_payload(),
    )

    assert payload["decision"]["status"] == "real_money_blocked"
    assert payload["decision"]["promote_to_real_money"] is False
    assert "execution_provenance_clean" in payload["decision"]["failed_checks"]
    assert "signal_provenance_clean" in payload["decision"]["failed_checks"]


def test_v204_blocks_legacy_execution_summary_without_recency_check() -> None:
    module = _load_module()
    execution_payload = _execution_payload()
    assert isinstance(execution_payload["checks"], dict)
    del execution_payload["checks"]["recent_execution_evidence_clean"]

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
        execution_payload=execution_payload,
        forward_freshness_payload={
            "decision": {
                "status": "forward_freshness_passed",
                "forward_data_current": True,
                "forward_evidence_available": True,
            }
        },
        public_data_payload=_public_data_payload(),
        readiness_input_hashes={"test_input": "test_hash"},
    )

    assert payload["decision"]["status"] == "real_money_blocked"
    assert payload["decision"]["promote_to_real_money"] is False
    assert "recent_execution_evidence_clean" in payload["decision"]["failed_checks"]


def test_v204_requires_v212_forward_freshness_even_when_legacy_forward_gate_passes() -> None:
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
        execution_payload=_execution_payload(),
        forward_freshness_payload={
            "decision": {
                "status": "forward_freshness_stale",
                "forward_data_current": False,
                "forward_evidence_available": False,
            }
        },
        public_data_payload=_public_data_payload(),
    )

    assert payload["decision"]["status"] == "real_money_blocked"
    assert payload["decision"]["promote_to_real_money"] is False
    assert "forward_freshness_clean" in payload["decision"]["failed_checks"]


def test_v204_requires_public_data_availability_even_when_other_gates_pass() -> None:
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
        execution_payload=_execution_payload(),
        forward_freshness_payload={
            "decision": {
                "status": "forward_freshness_passed",
                "forward_data_current": True,
                "forward_evidence_available": True,
            }
        },
        public_data_payload={
            "decision": {
                "status": "public_data_missing_local_files",
                "public_data_available": False,
                "failed_checks": ["published_files_downloaded"],
            }
        },
    )

    assert payload["decision"]["status"] == "real_money_blocked"
    assert payload["decision"]["promote_to_real_money"] is False
    assert "public_data_available" in payload["decision"]["failed_checks"]


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
        execution_payload=_execution_payload(),
        forward_freshness_payload={
            "decision": {
                "status": "forward_freshness_passed",
                "forward_data_current": True,
                "forward_evidence_available": True,
            }
        },
        public_data_payload=_public_data_payload(),
        readiness_input_hashes={"test_input": "test_hash"},
    )

    assert payload["decision"]["status"] == "real_money_ready"
    assert payload["decision"]["promote_to_real_money"] is True
    assert payload["decision"]["failed_checks"] == []
