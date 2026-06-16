from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from lob_microprice_lab.execution_kill_switch import KillSwitch, OrderIntent


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v208_kill_switch_self_test"
EVIDENCE_DIR = ROOT / "runs" / "research_v205_execution_validation"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V208_BTCUSDC_KILL_SWITCH_SELF_TEST.md"


def _dummy_order_intent() -> OrderIntent:
    return OrderIntent(
        timestamp="2026-06-16T00:00:00Z",
        symbol="BTCUSDC",
        side="buy",
        quantity=0.001,
        intended_price=100_000.0,
        dry_run=True,
    )


def _write_report(payload: dict[str, Any], *, event_path: Path, report_path: Path) -> None:
    decision = payload["decision"]
    event = payload["evidence"]["kill_switch_event"]
    lines = [
        "# Research V208 BTCUSDC Kill-Switch Self-Test",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Kill-switch self-test passed: `{decision['kill_switch_self_test_passed']}`",
        f"- Places live orders: `{decision['places_live_orders']}`",
        f"- Message: {decision['message']}",
        "",
        "## Evidence",
        "",
        f"- V205-compatible event CSV: `{event_path}`",
        f"- Event type: `{event['event_type']}`",
        f"- Allowed: `{event['allowed']}`",
        f"- Reason: `{event['reason']}`",
        f"- Would place order: `{event['would_place_order']}`",
        "",
        "## Iteration Metrics",
        "",
        "| Metric | V208 |",
        "|---|---:|",
        "| Strategy thresholds changed | No |",
        "| Entry/exit logic changed | No |",
        "| Leverage logic changed | No |",
        "| New backtest return improvement claimed | No |",
        "| Places live orders | No |",
        f"| Kill-switch self-test passed | {decision['kill_switch_self_test_passed']} |",
        "",
        "## Interpretation",
        "",
        "V208 does not trade, tune, or backtest. It creates local evidence that the kill switch can block a dummy BTCUSDC order intent before any live-order path is allowed.",
        "",
        "This only satisfies the kill-switch evidence part of V205. Real-money use remains blocked until clean fill and slippage evidence also exists.",
        "",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def run(*, out_dir: Path = OUT_DIR, evidence_dir: Path = EVIDENCE_DIR, report_path: Path = REPORT_PATH) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    decision = KillSwitch(active=True).authorize_order(_dummy_order_intent())
    event = decision.event
    event_path = evidence_dir / "kill_switch_events.csv"
    pd.DataFrame([event]).to_csv(event_path, index=False)

    passed = (
        decision.allowed is False
        and decision.reason == "kill_switch_active"
        and event.get("event_type") == "kill_switch_tested"
        and event.get("would_place_order") is False
    )
    payload = {
        "version": "v208_btcusdc_kill_switch_self_test",
        "config": {
            "changes_strategy_thresholds": False,
            "changes_entry_exit_logic": False,
            "changes_leverage_logic": False,
            "places_live_orders": False,
            "writes_v205_evidence": True,
        },
        "evidence": {
            "event_csv": str(event_path),
            "kill_switch_event": event,
        },
        "decision": {
            "status": "kill_switch_self_test_passed" if passed else "kill_switch_self_test_failed",
            "kill_switch_self_test_passed": passed,
            "places_live_orders": False,
            "message": (
                "Kill switch blocked the dummy order intent and wrote V205-compatible evidence."
                if passed
                else "Kill-switch self-test failed. Do not use real money."
            ),
        },
    }
    (out_dir / "v208_kill_switch_self_test_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, event_path=event_path, report_path=report_path)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run BTCUSDC kill-switch self-test evidence for V205.")
    parser.add_argument("--out", default=str(OUT_DIR))
    parser.add_argument("--evidence-dir", default=str(EVIDENCE_DIR))
    args = parser.parse_args()
    payload = run(out_dir=Path(args.out), evidence_dir=Path(args.evidence_dir))
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
