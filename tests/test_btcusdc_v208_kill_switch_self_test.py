from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

from lob_microprice_lab.execution_kill_switch import KillSwitch, OrderIntent


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v208_kill_switch_self_test.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v208_kill_switch_self_test", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _dummy_intent() -> OrderIntent:
    return OrderIntent(
        timestamp="2026-06-16T00:00:00Z",
        symbol="BTCUSDC",
        side="buy",
        quantity=0.001,
        intended_price=100_000.0,
        dry_run=True,
    )


def test_active_kill_switch_blocks_dummy_order_and_records_test_event() -> None:
    kill_switch = KillSwitch(active=True)

    decision = kill_switch.authorize_order(_dummy_intent())

    assert decision.allowed is False
    assert decision.reason == "kill_switch_active"
    assert decision.event["event_type"] == "kill_switch_tested"
    assert decision.event["symbol"] == "BTCUSDC"
    assert decision.event["would_place_order"] is False


def test_inactive_kill_switch_allows_only_dry_run_authorization() -> None:
    kill_switch = KillSwitch(active=False)

    decision = kill_switch.authorize_order(_dummy_intent())

    assert decision.allowed is True
    assert decision.reason == "dry_run_authorized"
    assert decision.event["event_type"] == "kill_switch_dry_run_authorized"
    assert decision.event["would_place_order"] is False


def test_v208_self_test_writes_v205_compatible_kill_switch_event_csv(tmp_path: Path) -> None:
    module = _load_module()
    report_path = tmp_path / "v208" / "report.md"

    payload = module.run(out_dir=tmp_path / "v208", evidence_dir=tmp_path / "v205", report_path=report_path)

    event_path = tmp_path / "v205" / "kill_switch_events.csv"
    events = pd.read_csv(event_path)
    assert payload["decision"]["kill_switch_self_test_passed"] is True
    assert payload["decision"]["places_live_orders"] is False
    assert events["event_type"].tolist() == ["kill_switch_tested"]
    assert report_path.exists()
    assert str(event_path) in report_path.read_text(encoding="utf-8")
