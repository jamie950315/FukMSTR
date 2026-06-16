from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v211_signal_provenance_gate.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v211_signal_provenance_gate", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fill_audit(signal_source: str) -> pd.DataFrame:
    return pd.DataFrame(
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
            "signal_source": [signal_source] * 32,
            "market_source": ["binance-public-spot"] * 32,
        }
    )


def test_v211_blocks_manual_signal_source_even_when_execution_provenance_is_clean(tmp_path: Path) -> None:
    module = _load_module()
    fills_path = tmp_path / "fill_audit.csv"
    kill_switch_path = tmp_path / "kill_switch_events.csv"
    report_path = tmp_path / "report.md"
    _fill_audit("manual").to_csv(fills_path, index=False)
    pd.DataFrame({"event_type": ["kill_switch_tested"]}).to_csv(kill_switch_path, index=False)

    payload = module.run(
        fills_path=fills_path,
        kill_switch_path=kill_switch_path,
        out_dir=tmp_path / "out",
        report_path=report_path,
    )

    assert payload["decision"]["status"] == "signal_provenance_blocked"
    assert payload["decision"]["promote_to_real_money"] is False
    assert "signal_provenance_clean" in payload["decision"]["failed_checks"]
    assert payload["config"]["changes_strategy_thresholds"] is False
    assert payload["config"]["places_live_orders"] is False
    assert "Signal provenance clean" in report_path.read_text(encoding="utf-8")


def test_v211_passes_clean_realtime_signal_source_without_promoting_real_money(tmp_path: Path) -> None:
    module = _load_module()
    fills_path = tmp_path / "fill_audit.csv"
    kill_switch_path = tmp_path / "kill_switch_events.csv"
    report_path = tmp_path / "report.md"
    _fill_audit("paper_shadow_realtime_signal").to_csv(fills_path, index=False)
    pd.DataFrame({"event_type": ["kill_switch_tested"]}).to_csv(kill_switch_path, index=False)

    payload = module.run(
        fills_path=fills_path,
        kill_switch_path=kill_switch_path,
        out_dir=tmp_path / "out",
        report_path=report_path,
    )

    assert payload["decision"]["status"] == "signal_provenance_passed"
    assert payload["decision"]["promote_to_real_money"] is False
