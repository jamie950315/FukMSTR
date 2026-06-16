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
            "requires_forward_freshness": True,
        },
        "checks": {
            "forward_freshness_clean": True,
        },
        "evidence": {
            "forward_freshness_status": "forward_freshness_passed",
            "forward_data_current": True,
            "fresh_forward_evidence_available": True,
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
