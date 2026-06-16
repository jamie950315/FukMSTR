from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v206_real_money_launch_preflight.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v206_real_money_launch_preflight", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _ready_payload() -> dict[str, object]:
    return {
        "config": {
            "min_execution_fills": 30,
            "requires_forward_freshness": True,
            "requires_public_data_availability": True,
            "requires_execution_validation": True,
            "requires_execution_provenance": True,
            "requires_signal_provenance": True,
            "requires_readiness_source_provenance": True,
        },
        "checks": {
            "readiness_source_provenance_clean": True,
            "forward_freshness_clean": True,
            "public_data_available": True,
            "execution_validation_passed": True,
            "execution_fill_evidence_available": True,
            "filled_status_clean": True,
            "execution_provenance_clean": True,
            "signal_provenance_clean": True,
            "execution_slippage_p95_clean": True,
            "execution_kill_switch_tested": True,
            "execution_secrets_absent_from_repo": True,
        },
        "evidence": {
            "forward_freshness_status": "forward_freshness_passed",
            "forward_data_current": True,
            "fresh_forward_evidence_available": True,
            "public_data_status": "public_data_availability_passed",
            "public_data_available": True,
            "execution_validation_passed": True,
            "execution_fill_count": 30,
            "execution_fill_evidence_available": True,
            "filled_status_clean": True,
            "execution_provenance_clean": True,
            "signal_provenance_clean": True,
            "execution_slippage_p95_clean": True,
            "execution_kill_switch_tested": True,
            "execution_secrets_absent_from_repo": True,
            "readiness_source_commit": "test-source-commit",
            "readiness_runtime_source_clean": True,
            "readiness_dirty_runtime_path_count": 0,
            "readiness_dirty_runtime_paths": [],
        },
        "decision": {
            "status": "real_money_ready",
            "promote_to_real_money": True,
            "failed_checks": [],
        }
    }


def test_v206_blocks_real_money_launch_when_v204_is_blocked() -> None:
    module = _load_module()

    payload = module._preflight_payload(
        readiness_payload={
            "decision": {
                "status": "real_money_blocked",
                "promote_to_real_money": False,
                "failed_checks": ["forward_evidence_available"],
            }
        },
        arm_token=module.REQUIRED_ARM_TOKEN,
        dirty_runtime_paths=[],
    )

    assert payload["decision"]["status"] == "real_money_launch_blocked"
    assert payload["decision"]["allow_real_money_launch"] is False
    assert "readiness_gate_passed" in payload["decision"]["failed_checks"]


def test_v206_blocks_real_money_launch_without_explicit_arm_token() -> None:
    module = _load_module()

    payload = module._preflight_payload(
        readiness_payload=_ready_payload(),
        arm_token="",
        dirty_runtime_paths=[],
    )

    assert payload["decision"]["allow_real_money_launch"] is False
    assert "explicit_real_money_arm" in payload["decision"]["failed_checks"]


def test_v206_blocks_real_money_launch_when_runtime_source_is_dirty() -> None:
    module = _load_module()

    payload = module._preflight_payload(
        readiness_payload=_ready_payload(),
        arm_token=module.REQUIRED_ARM_TOKEN,
        dirty_runtime_paths=["src/lob_microprice_lab/paper_trading.py"],
    )

    assert payload["decision"]["allow_real_money_launch"] is False
    assert "runtime_source_clean" in payload["decision"]["failed_checks"]


def test_v206_blocks_legacy_ready_summary_without_v212_forward_freshness() -> None:
    module = _load_module()

    payload = module._preflight_payload(
        readiness_payload={
            "decision": {
                "status": "real_money_ready",
                "promote_to_real_money": True,
                "failed_checks": [],
            }
        },
        arm_token=module.REQUIRED_ARM_TOKEN,
        dirty_runtime_paths=[],
    )

    assert payload["decision"]["allow_real_money_launch"] is False
    assert "readiness_forward_freshness_clean" in payload["decision"]["failed_checks"]


def test_v206_blocks_ready_summary_without_v214_public_data_availability() -> None:
    module = _load_module()
    readiness_payload = _ready_payload()
    assert isinstance(readiness_payload["checks"], dict)
    assert isinstance(readiness_payload["evidence"], dict)
    del readiness_payload["checks"]["public_data_available"]
    del readiness_payload["evidence"]["public_data_status"]
    del readiness_payload["evidence"]["public_data_available"]

    payload = module._preflight_payload(
        readiness_payload=readiness_payload,
        arm_token=module.REQUIRED_ARM_TOKEN,
        dirty_runtime_paths=[],
    )

    assert payload["decision"]["allow_real_money_launch"] is False
    assert "readiness_public_data_available" in payload["decision"]["failed_checks"]


def test_v206_blocks_ready_summary_without_v216_execution_provenance() -> None:
    module = _load_module()
    readiness_payload = _ready_payload()
    assert isinstance(readiness_payload["config"], dict)
    assert isinstance(readiness_payload["checks"], dict)
    assert isinstance(readiness_payload["evidence"], dict)
    del readiness_payload["config"]["requires_execution_provenance"]
    del readiness_payload["checks"]["execution_provenance_clean"]
    del readiness_payload["evidence"]["execution_provenance_clean"]

    payload = module._preflight_payload(
        readiness_payload=readiness_payload,
        arm_token=module.REQUIRED_ARM_TOKEN,
        dirty_runtime_paths=[],
    )

    assert payload["decision"]["allow_real_money_launch"] is False
    assert "readiness_execution_provenance_clean" in payload["decision"]["failed_checks"]


def test_v206_blocks_ready_summary_without_v218_source_provenance() -> None:
    module = _load_module()
    readiness_payload = _ready_payload()
    assert isinstance(readiness_payload["config"], dict)
    assert isinstance(readiness_payload["checks"], dict)
    assert isinstance(readiness_payload["evidence"], dict)
    del readiness_payload["config"]["requires_readiness_source_provenance"]
    del readiness_payload["checks"]["readiness_source_provenance_clean"]
    del readiness_payload["evidence"]["readiness_source_commit"]

    payload = module._preflight_payload(
        readiness_payload=readiness_payload,
        arm_token=module.REQUIRED_ARM_TOKEN,
        dirty_runtime_paths=[],
    )

    assert payload["decision"]["allow_real_money_launch"] is False
    assert "readiness_source_provenance_clean" in payload["decision"]["failed_checks"]


def test_v206_blocks_ready_summary_from_different_source_commit() -> None:
    module = _load_module()
    readiness_payload = _ready_payload()
    assert isinstance(readiness_payload["evidence"], dict)
    readiness_payload["evidence"]["readiness_source_commit"] = "old-source-commit"

    payload = module._preflight_payload(
        readiness_payload=readiness_payload,
        arm_token=module.REQUIRED_ARM_TOKEN,
        dirty_runtime_paths=[],
        current_source_commit="test-source-commit",
    )

    assert payload["decision"]["allow_real_money_launch"] is False
    assert "readiness_source_provenance_clean" in payload["decision"]["failed_checks"]


def test_v206_passes_only_when_readiness_arm_and_runtime_source_are_clean() -> None:
    module = _load_module()

    payload = module._preflight_payload(
        readiness_payload=_ready_payload(),
        arm_token=module.REQUIRED_ARM_TOKEN,
        dirty_runtime_paths=[],
    )

    assert payload["decision"]["status"] == "real_money_launch_preflight_passed"
    assert payload["decision"]["allow_real_money_launch"] is True
    assert payload["decision"]["failed_checks"] == []
