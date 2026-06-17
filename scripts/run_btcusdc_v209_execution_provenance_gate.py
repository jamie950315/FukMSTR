from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v209_execution_provenance_gate"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V209_BTCUSDC_EXECUTION_PROVENANCE_GATE.md"
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
    if "execution_provenance_clean" in failed:
        return "execution_provenance_blocked"
    if v205_payload["decision"]["execution_validation_passed"] is True:
        return "execution_provenance_passed"
    return "execution_provenance_waiting_for_fill_evidence"


def _write_report(payload: dict[str, Any], *, report_path: Path) -> None:
    decision = payload["decision"]
    evidence = payload["evidence"]
    checks = payload["checks"]
    lines = [
        "# Research V209 BTCUSDC Execution Provenance Gate",
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
        f"| Paper-shadow capture summary clean | {checks['paper_shadow_capture_summary_clean']} | status={evidence['paper_shadow_capture_summary_status']}; reason={evidence['paper_shadow_capture_summary_reason']} |",
        f"| Filled status clean | {checks['filled_status_clean']} | requires every fill status to be `filled` |",
        f"| Slippage p95 clean | {checks['slippage_p95_clean']} | max_slippage_bps_p95={decision['max_slippage_bps_p95']} |",
        f"| Kill switch tested | {checks['kill_switch_tested']} | kill_switch_event_count={evidence['kill_switch_event_count']} |",
        f"| Secrets absent from repo | {checks['secrets_absent_from_repo']} | secret_finding_count={evidence['secret_finding_count']} |",
        "",
        "## Iteration Metrics",
        "",
        "| Metric | V209 |",
        "|---|---:|",
        "| Strategy thresholds changed | No |",
        "| Entry/exit logic changed | No |",
        "| Leverage logic changed | No |",
        "| New backtest return improvement claimed | No |",
        "| Places live orders | No |",
        f"| Execution provenance clean | {checks['execution_provenance_clean']} |",
        f"| Signal provenance clean | {checks['signal_provenance_clean']} |",
        f"| Promote to real money | {decision['promote_to_real_money']} |",
        "",
        "## Interpretation",
        "",
        "V209 tightens execution evidence admission. Clean-looking fills are not enough; real-money readiness now requires order-level provenance and signal provenance.",
        "",
        "This does not create trades or claim new profitability. It prevents synthetic or backtest-like fill rows from satisfying the real-money execution gate.",
        "",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def run(
    *,
    fills_path: Path | None = None,
    kill_switch_path: Path | None = None,
    capture_summary_path: Path | None = None,
    out_dir: Path = OUT_DIR,
    report_path: Path = REPORT_PATH,
) -> dict[str, Any]:
    v205 = _load_v205_module()
    fills_path = Path(fills_path) if fills_path is not None else v205.DEFAULT_FILLS
    kill_switch_path = Path(kill_switch_path) if kill_switch_path is not None else v205.DEFAULT_KILL_SWITCH_EVENTS
    capture_summary_path = (
        Path(capture_summary_path) if capture_summary_path is not None else v205.DEFAULT_CAPTURE_SUMMARY
    )
    v205_payload = v205._execution_validation_payload(
        fills=v205._read_csv_or_empty(fills_path),
        kill_switch_events=v205._read_csv_or_empty(kill_switch_path),
        secret_findings=v205._scan_repo_for_secret_findings(),
        capture_summary=v205._read_json_or_empty(capture_summary_path),
    )
    status = _status_from_v205(v205_payload)
    passed = status == "execution_provenance_passed"
    payload = {
        "version": "v209_btcusdc_execution_provenance_gate",
        "config": {
            "changes_strategy_thresholds": False,
            "changes_entry_exit_logic": False,
            "changes_leverage_logic": False,
            "places_live_orders": False,
            "required_provenance_columns": sorted(v205.PROVENANCE_FILL_COLUMNS),
            "allowed_execution_modes": sorted(v205.ALLOWED_EXECUTION_MODES),
        },
        "inputs": {
            "fill_audit_csv": str(fills_path),
            "kill_switch_event_csv": str(kill_switch_path),
            "capture_summary_json": str(capture_summary_path),
        },
        "evidence": v205_payload["evidence"],
        "checks": v205_payload["checks"],
        "decision": {
            "status": status,
            "promote_to_real_money": passed,
            "failed_checks": v205_payload["decision"]["failed_checks"],
            "max_slippage_bps_p95": v205_payload["decision"]["max_slippage_bps_p95"],
            "message": (
                "Execution evidence provenance is clean."
                if passed
                else "Do not use real money. Execution evidence provenance is missing or failed."
            ),
        },
        "v205_decision": v205_payload["decision"],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "v209_execution_provenance_gate_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, report_path=report_path)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate BTCUSDC execution evidence provenance for real-money readiness.")
    parser.add_argument("--fills", default=None)
    parser.add_argument("--kill-switch-events", default=None)
    parser.add_argument("--capture-summary", default=None)
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args()
    payload = run(
        fills_path=Path(args.fills) if args.fills else None,
        kill_switch_path=Path(args.kill_switch_events) if args.kill_switch_events else None,
        capture_summary_path=Path(args.capture_summary) if args.capture_summary else None,
        out_dir=Path(args.out),
    )
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
