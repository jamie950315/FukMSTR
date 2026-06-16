from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v211_signal_provenance_gate"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V211_BTCUSDC_SIGNAL_PROVENANCE_GATE.md"
V205_SCRIPT = ROOT / "scripts" / "run_btcusdc_v205_execution_validation.py"


def _load_v205_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v205_execution_validation", V205_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {V205_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _status_from_v205(v205_payload: dict[str, Any]) -> str:
    failed = set(v205_payload["decision"]["failed_checks"])
    if "signal_provenance_clean" in failed:
        return "signal_provenance_blocked"
    if v205_payload["checks"].get("signal_provenance_clean") is True:
        return "signal_provenance_passed"
    return "signal_provenance_waiting_for_fill_evidence"


def _write_report(payload: dict[str, Any], *, report_path: Path) -> None:
    decision = payload["decision"]
    evidence = payload["evidence"]
    checks = payload["checks"]
    lines = [
        "# Research V211 BTCUSDC Signal Provenance Gate",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to real money: `{decision['promote_to_real_money']}`",
        f"- Failed checks: `{', '.join(decision['failed_checks']) if decision['failed_checks'] else 'none'}`",
        f"- Message: {decision['message']}",
        "",
        "## Gate Checks",
        "",
        "| Check | Passed | Evidence |",
        "|---|---:|---|",
        f"| Fill evidence available | {checks['fill_evidence_available']} | fill_count={evidence['fill_count']}; missing_base_columns={evidence['missing_base_fill_columns']} |",
        f"| Execution provenance clean | {checks['execution_provenance_clean']} | missing_provenance_columns={evidence['missing_provenance_columns']} |",
        f"| Signal provenance clean | {checks['signal_provenance_clean']} | missing_signal_provenance_columns={evidence['missing_signal_provenance_columns']} |",
        "",
        "## Iteration Metrics",
        "",
        "| Metric | V211 |",
        "|---|---:|",
        "| Strategy thresholds changed | No |",
        "| Entry/exit logic changed | No |",
        "| Leverage logic changed | No |",
        "| New backtest return improvement claimed | No |",
        "| Places live orders | No |",
        f"| Signal provenance clean | {checks['signal_provenance_clean']} |",
        f"| Promote to real money | {decision['promote_to_real_money']} |",
        "",
        "## Interpretation",
        "",
        "V211 prevents manual, synthetic, backtest, unknown, or blank signal/market sources from satisfying the execution-evidence path. Clean order-looking rows are not enough unless the signal source is also causal and auditable.",
        "",
        "This does not create trades, tune thresholds, or claim new profitability. Real-money use remains blocked until V204 passes with current forward and execution evidence.",
        "",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def run(
    *,
    fills_path: Path | None = None,
    kill_switch_path: Path | None = None,
    out_dir: Path = OUT_DIR,
    report_path: Path = REPORT_PATH,
) -> dict[str, Any]:
    v205 = _load_v205_module()
    fills_path = Path(fills_path) if fills_path is not None else v205.DEFAULT_FILLS
    kill_switch_path = Path(kill_switch_path) if kill_switch_path is not None else v205.DEFAULT_KILL_SWITCH_EVENTS
    v205_payload = v205._execution_validation_payload(
        fills=v205._read_csv_or_empty(fills_path),
        kill_switch_events=v205._read_csv_or_empty(kill_switch_path),
        secret_findings=v205._scan_repo_for_secret_findings(),
    )
    status = _status_from_v205(v205_payload)
    failed_checks = []
    if status != "signal_provenance_passed":
        failed_checks.append("signal_provenance_clean")
    payload = {
        "version": "v211_btcusdc_signal_provenance_gate",
        "config": {
            "changes_strategy_thresholds": False,
            "changes_entry_exit_logic": False,
            "changes_leverage_logic": False,
            "places_live_orders": False,
            "required_signal_provenance_columns": sorted(v205.SIGNAL_PROVENANCE_COLUMNS),
            "blocked_signal_sources": sorted(v205.BLOCKED_SIGNAL_SOURCES),
            "blocked_market_sources": sorted(v205.BLOCKED_MARKET_SOURCES),
        },
        "inputs": {
            "fill_audit_csv": str(fills_path),
            "kill_switch_event_csv": str(kill_switch_path),
        },
        "evidence": v205_payload["evidence"],
        "checks": v205_payload["checks"],
        "decision": {
            "status": status,
            "promote_to_real_money": False,
            "failed_checks": failed_checks,
            "message": (
                "Signal provenance is clean, but V211 alone does not promote real-money use."
                if status == "signal_provenance_passed"
                else "Do not use real money. Signal provenance is missing or failed."
            ),
        },
        "v205_decision": v205_payload["decision"],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "v211_signal_provenance_gate_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, report_path=report_path)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate BTCUSDC signal provenance for execution evidence.")
    parser.add_argument("--fills", default=None)
    parser.add_argument("--kill-switch-events", default=None)
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args()
    payload = run(
        fills_path=Path(args.fills) if args.fills else None,
        kill_switch_path=Path(args.kill_switch_events) if args.kill_switch_events else None,
        out_dir=Path(args.out),
    )
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
