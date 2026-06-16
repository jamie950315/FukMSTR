from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v214_public_data_availability_gate.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v214_public_data_availability_gate", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v214_passes_when_latest_completed_utc_day_is_published_and_local() -> None:
    module = _load_module()

    payload = module._payload_for_public_data_availability(
        latest_completed_utc_date="2026-06-15",
        remote_status={
            "2026-06-15": {
                "aggtrade_http_status": 200,
                "kline_http_status": 200,
            }
        },
        local_aggtrade_dates={"2026-06-15"},
        local_kline_dates={"2026-06-15"},
    )

    assert payload["decision"]["status"] == "public_data_availability_passed"
    assert payload["decision"]["public_data_available"] is True
    assert payload["decision"]["failed_checks"] == []


def test_v214_blocks_when_remote_file_is_published_but_local_file_is_missing() -> None:
    module = _load_module()

    payload = module._payload_for_public_data_availability(
        latest_completed_utc_date="2026-06-15",
        remote_status={
            "2026-06-15": {
                "aggtrade_http_status": 200,
                "kline_http_status": 200,
            }
        },
        local_aggtrade_dates={"2026-06-15"},
        local_kline_dates=set(),
    )

    assert payload["decision"]["status"] == "public_data_missing_local_files"
    assert payload["decision"]["public_data_available"] is False
    assert "published_files_downloaded" in payload["decision"]["failed_checks"]
    assert payload["evidence"]["missing_local_kline_dates"] == ["2026-06-15"]


def test_v214_blocks_when_latest_completed_utc_day_is_not_published_yet() -> None:
    module = _load_module()

    payload = module._payload_for_public_data_availability(
        latest_completed_utc_date="2026-06-15",
        remote_status={
            "2026-06-15": {
                "aggtrade_http_status": 404,
                "kline_http_status": 404,
            }
        },
        local_aggtrade_dates={"2026-06-14"},
        local_kline_dates={"2026-06-14"},
    )

    assert payload["decision"]["status"] == "public_data_pending_publication"
    assert payload["decision"]["public_data_available"] is False
    assert "latest_completed_utc_day_published" in payload["decision"]["failed_checks"]
