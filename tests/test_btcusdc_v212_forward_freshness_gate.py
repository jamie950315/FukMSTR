from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v212_forward_freshness_gate.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v212_forward_freshness_gate", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _v90_payload(*, combined_end: str, new_signal_count: int, status: str = "no_signal") -> dict[str, object]:
    return {
        "version": "v90_btcusdc_forward_monitoring",
        "data": {
            "combined_end": combined_end,
            "new_aggtrade_file_count": 5,
        },
        "decision": {
            "new_signal_count": new_signal_count,
            "status": status,
            "next_action": "continue_monitoring",
        },
    }


def test_v212_blocks_when_v90_data_is_older_than_latest_public_file() -> None:
    module = _load_module()

    payload = module._payload_for_forward_freshness(
        v90_payload=_v90_payload(combined_end="2026-06-14T23:59:00+00:00", new_signal_count=12, status="passed"),
        latest_public_file_date="2026-06-15",
    )

    assert payload["decision"]["status"] == "forward_freshness_stale"
    assert payload["decision"]["forward_data_current"] is False
    assert payload["decision"]["forward_evidence_available"] is False
    assert payload["decision"]["promote_to_real_money"] is False
    assert "forward_data_current" in payload["decision"]["failed_checks"]


def test_v212_keeps_current_no_signal_data_from_counting_as_forward_evidence() -> None:
    module = _load_module()

    payload = module._payload_for_forward_freshness(
        v90_payload=_v90_payload(combined_end="2026-06-15T23:59:00+00:00", new_signal_count=0),
        latest_public_file_date="2026-06-15",
    )

    assert payload["decision"]["status"] == "forward_fresh_no_signal"
    assert payload["decision"]["forward_data_current"] is True
    assert payload["decision"]["forward_evidence_available"] is False
    assert payload["decision"]["promote_to_real_money"] is False
    assert "forward_evidence_available" in payload["decision"]["failed_checks"]


def test_v212_requires_enough_current_forward_signals_before_marking_evidence_available() -> None:
    module = _load_module()

    payload = module._payload_for_forward_freshness(
        v90_payload=_v90_payload(combined_end="2026-06-15T23:59:00+00:00", new_signal_count=30, status="passed"),
        latest_public_file_date="2026-06-15",
    )

    assert payload["decision"]["status"] == "forward_freshness_passed"
    assert payload["decision"]["forward_data_current"] is True
    assert payload["decision"]["forward_evidence_available"] is True
    assert payload["decision"]["promote_to_real_money"] is False
    assert payload["decision"]["failed_checks"] == []
