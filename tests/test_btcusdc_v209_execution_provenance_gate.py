from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v209_execution_provenance_gate.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v209_execution_provenance_gate", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v209_blocks_fill_audit_without_execution_provenance(tmp_path: Path) -> None:
    module = _load_module()
    fills_path = tmp_path / "fill_audit.csv"
    kill_switch_path = tmp_path / "kill_switch_events.csv"
    report_path = tmp_path / "report.md"

    pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-06-16T00:00:00Z", periods=32, freq="min"),
            "symbol": ["BTCUSDC"] * 32,
            "side": [1, -1] * 16,
            "intended_price": [100_000.0] * 32,
            "fill_price": [100_020.0] * 32,
            "status": ["filled"] * 32,
        }
    ).to_csv(fills_path, index=False)
    pd.DataFrame({"event_type": ["kill_switch_tested"]}).to_csv(kill_switch_path, index=False)

    payload = module.run(
        fills_path=fills_path,
        kill_switch_path=kill_switch_path,
        out_dir=tmp_path / "out",
        report_path=report_path,
    )

    assert payload["decision"]["status"] == "execution_provenance_blocked"
    assert payload["decision"]["promote_to_real_money"] is False
    assert "execution_provenance_clean" in payload["decision"]["failed_checks"]
    assert payload["config"]["changes_strategy_thresholds"] is False
    assert payload["config"]["places_live_orders"] is False
    assert "Strategy thresholds changed | No" in report_path.read_text(encoding="utf-8")
    assert "Signal provenance clean" in report_path.read_text(encoding="utf-8")
