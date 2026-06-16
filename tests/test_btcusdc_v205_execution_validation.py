from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v205_execution_validation.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v205_execution_validation", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v205_blocks_when_fill_evidence_is_missing() -> None:
    module = _load_module()

    payload = module._execution_validation_payload(
        fills=pd.DataFrame(),
        kill_switch_events=pd.DataFrame({"event_type": ["kill_switch_tested"]}),
        secret_findings=[],
    )

    assert payload["decision"]["status"] == "execution_validation_missing_evidence"
    assert payload["decision"]["execution_validation_passed"] is False
    assert "fill_evidence_available" in payload["decision"]["failed_checks"]


def test_v205_blocks_when_kill_switch_was_not_tested() -> None:
    module = _load_module()
    fills = pd.DataFrame(
        {
            "timestamp": ["2026-06-16T00:00:00Z", "2026-06-16T00:01:00Z"],
            "symbol": ["BTCUSDC", "BTCUSDC"],
            "side": [1, -1],
            "intended_price": [100_000.0, 100_100.0],
            "fill_price": [100_010.0, 100_090.0],
            "status": ["filled", "filled"],
        }
    )

    payload = module._execution_validation_payload(
        fills=fills,
        kill_switch_events=pd.DataFrame(),
        secret_findings=[],
    )

    assert payload["decision"]["execution_validation_passed"] is False
    assert "kill_switch_tested" in payload["decision"]["failed_checks"]


def test_v205_blocks_clean_looking_fills_without_execution_provenance() -> None:
    module = _load_module()
    fills = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-06-16T00:00:00Z", periods=32, freq="min"),
            "symbol": ["BTCUSDC"] * 32,
            "side": [1, -1] * 16,
            "intended_price": [100_000.0] * 32,
            "fill_price": [100_020.0] * 32,
            "status": ["filled"] * 32,
        }
    )
    kill_switch_events = pd.DataFrame({"event_type": ["kill_switch_tested"]})

    payload = module._execution_validation_payload(
        fills=fills,
        kill_switch_events=kill_switch_events,
        secret_findings=[],
    )

    assert payload["decision"]["execution_validation_passed"] is False
    assert "execution_provenance_clean" in payload["decision"]["failed_checks"]
    assert payload["checks"]["execution_provenance_clean"] is False


def test_v205_passes_only_with_clean_fills_kill_switch_and_no_secrets() -> None:
    module = _load_module()
    fills = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-06-16T00:00:00Z", periods=32, freq="min"),
            "symbol": ["BTCUSDC"] * 32,
            "side": [1, -1] * 16,
            "intended_price": [100_000.0] * 32,
            "fill_price": [100_020.0] * 32,
            "status": ["filled"] * 32,
            "venue": ["binance"] * 32,
            "execution_mode": ["paper_shadow_live"] * 32,
            "evidence_source": ["live_capture"] * 32,
            "capture_id": ["capture-20260616"] * 32,
            "order_id": [f"order-{idx}" for idx in range(32)],
            "client_order_id": [f"client-{idx}" for idx in range(32)],
            "exchange_timestamp": pd.date_range("2026-06-16T00:00:01Z", periods=32, freq="min"),
            "signal_id": [f"sig-{idx}" for idx in range(32)],
            "signal_source": ["unit_realtime_signal"] * 32,
            "market_source": ["binance-public-spot"] * 32,
        }
    )
    kill_switch_events = pd.DataFrame({"event_type": ["startup", "kill_switch_tested"]})

    payload = module._execution_validation_payload(
        fills=fills,
        kill_switch_events=kill_switch_events,
        secret_findings=[],
    )

    assert payload["decision"]["status"] == "execution_validation_passed"
    assert payload["decision"]["execution_validation_passed"] is True
    assert payload["decision"]["kill_switch_tested"] is True
    assert payload["decision"]["secrets_present_in_repo"] is False
    assert payload["decision"]["max_slippage_bps_p95"] == 2.0


def test_v205_blocks_manual_or_backtest_signal_sources_even_with_clean_execution_rows() -> None:
    module = _load_module()
    fills = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-06-16T00:00:00Z", periods=32, freq="min"),
            "symbol": ["BTCUSDC"] * 32,
            "side": [1, -1] * 16,
            "intended_price": [100_000.0] * 32,
            "fill_price": [100_020.0] * 32,
            "status": ["filled"] * 32,
            "venue": ["binance"] * 32,
            "execution_mode": ["paper_shadow_live"] * 32,
            "evidence_source": ["live_capture"] * 32,
            "capture_id": ["capture-20260616"] * 32,
            "order_id": [f"order-{idx}" for idx in range(32)],
            "client_order_id": [f"client-{idx}" for idx in range(32)],
            "exchange_timestamp": pd.date_range("2026-06-16T00:00:01Z", periods=32, freq="min"),
            "signal_id": [f"sig-{idx}" for idx in range(32)],
            "signal_source": ["manual"] * 32,
            "market_source": ["binance-public-spot"] * 32,
        }
    )
    kill_switch_events = pd.DataFrame({"event_type": ["startup", "kill_switch_tested"]})

    payload = module._execution_validation_payload(
        fills=fills,
        kill_switch_events=kill_switch_events,
        secret_findings=[],
    )

    assert payload["decision"]["execution_validation_passed"] is False
    assert "signal_provenance_clean" in payload["decision"]["failed_checks"]
    assert payload["checks"]["signal_provenance_clean"] is False
