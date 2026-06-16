from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v204_real_money_readiness_gate"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V204_BTCUSDC_REAL_MONEY_READINESS_GATE.md"
V195_SUMMARY = ROOT / "runs" / "research_v195_post_goal_overfitting_audit" / "v195_post_goal_overfitting_audit_summary.json"
V196_SUMMARY = ROOT / "runs" / "research_v196_forward_monitoring_gate" / "v196_forward_monitoring_gate_summary.json"
V212_SUMMARY = ROOT / "runs" / "research_v212_forward_freshness_gate" / "v212_forward_freshness_gate_summary.json"
V214_SUMMARY = ROOT / "runs" / "research_v214_public_data_availability_gate" / "v214_public_data_availability_gate_summary.json"
REALTIME_SMOKE_SUMMARY = ROOT / "runs" / "paper_v142_realtime_safe_smoke" / "summary.json"
EXECUTION_VALIDATION_SUMMARY = (
    ROOT / "runs" / "research_v204_real_money_execution_validation" / "execution_validation_summary.json"
)

MIN_FORWARD_TRADES = 30
MAX_EXECUTION_SLIPPAGE_BPS_P95 = 5.0
MIN_EXECUTION_FILLS = 30
RUNTIME_PREFIXES = (
    "src/",
    "scripts/",
    "tests/",
    "Makefile",
    "pyproject.toml",
    "requirements.txt",
)


def _decision(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    decision = payload.get("decision", {})
    return decision if isinstance(decision, dict) else {}


def _checks(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    checks = payload.get("checks", {})
    return checks if isinstance(checks, dict) else {}


def _evidence(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    evidence = payload.get("evidence", {})
    return evidence if isinstance(evidence, dict) else {}


def _current_git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "git_commit_unavailable"
    return result.stdout.strip() or "git_commit_unavailable"


def _dirty_runtime_paths_from_git() -> list[str]:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ["git_status_unavailable"]
    dirty: list[str] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path.startswith(RUNTIME_PREFIXES) or path in RUNTIME_PREFIXES:
            dirty.append(path)
    return sorted(set(dirty))


def _file_sha256(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return "missing"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _readiness_input_hashes(inputs: dict[str, str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name, raw_path in sorted(inputs.items()):
        hashes[name] = _file_sha256(Path(raw_path))
    return hashes


def _payload_for_readiness(
    *,
    overfit_payload: dict[str, Any] | None,
    forward_payload: dict[str, Any] | None,
    realtime_summary: dict[str, Any] | None,
    execution_payload: dict[str, Any] | None,
    forward_freshness_payload: dict[str, Any] | None = None,
    public_data_payload: dict[str, Any] | None = None,
    source_commit: str = "test-source-commit",
    dirty_runtime_paths: list[str] | None = None,
    readiness_input_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    overfit = _decision(overfit_payload)
    forward = _decision(forward_payload)
    execution = _decision(execution_payload)
    execution_checks = _checks(execution_payload)
    execution_evidence = _evidence(execution_payload)
    forward_freshness = _decision(forward_freshness_payload)
    public_data = _decision(public_data_payload)
    realtime = realtime_summary if isinstance(realtime_summary, dict) else {}
    execution_slippage = float(execution.get("max_slippage_bps_p95", 999.0) or 999.0)
    dirty_paths = dirty_runtime_paths if dirty_runtime_paths is not None else []
    readiness_source_clean = source_commit not in {"", "git_commit_unavailable"} and not dirty_paths
    inputs = {
        "overfit_audit": str(V195_SUMMARY),
        "forward_monitoring": str(V196_SUMMARY),
        "forward_freshness": str(V212_SUMMARY),
        "public_data_availability": str(V214_SUMMARY),
        "realtime_smoke": str(REALTIME_SMOKE_SUMMARY),
        "execution_validation": str(EXECUTION_VALIDATION_SUMMARY),
    }
    input_hashes = readiness_input_hashes if readiness_input_hashes is not None else {}
    input_hashes_clean = bool(input_hashes) and all(value not in {"", "missing"} for value in input_hashes.values())

    checks = {
        "readiness_source_provenance_clean": readiness_source_clean,
        "readiness_input_hashes_clean": input_hashes_clean,
        "historical_optimization_frozen_clean": (
            overfit.get("status") == "post_goal_overfitting_not_detected"
            and overfit.get("stop_historical_optimization") is False
        ),
        "forward_evidence_available": (
            forward.get("forward_evidence_available") is True
            and int(forward.get("forward_trade_count", 0) or 0) >= MIN_FORWARD_TRADES
        ),
        "forward_freshness_clean": (
            forward_freshness.get("status") == "forward_freshness_passed"
            and forward_freshness.get("forward_data_current") is True
            and forward_freshness.get("forward_evidence_available") is True
        ),
        "public_data_available": (
            public_data.get("status") == "public_data_availability_passed"
            and public_data.get("public_data_available") is True
        ),
        "realtime_smoke_clean": (
            int(realtime.get("rejected_signals", 0) or 0) == 0
            and int(realtime.get("market_data_errors", 0) or 0) == 0
        ),
        "execution_validation_passed": (
            execution.get("status") == "execution_validation_passed"
            and execution.get("execution_validation_passed") is True
            and not execution.get("failed_checks", [])
            and execution.get("kill_switch_tested") is True
            and execution.get("secrets_present_in_repo") is False
            and execution_slippage <= MAX_EXECUTION_SLIPPAGE_BPS_P95
        ),
        "execution_fill_evidence_available": (
            execution_checks.get("fill_evidence_available") is True
            and int(execution_evidence.get("fill_count", 0) or 0) >= MIN_EXECUTION_FILLS
        ),
        "filled_status_clean": execution_checks.get("filled_status_clean") is True,
        "execution_provenance_clean": execution_checks.get("execution_provenance_clean") is True,
        "signal_provenance_clean": execution_checks.get("signal_provenance_clean") is True,
        "execution_slippage_p95_clean": (
            execution_checks.get("slippage_p95_clean") is True
            and execution_slippage <= MAX_EXECUTION_SLIPPAGE_BPS_P95
        ),
        "execution_kill_switch_tested": (
            execution_checks.get("kill_switch_tested") is True
            and execution.get("kill_switch_tested") is True
        ),
        "execution_secrets_absent_from_repo": (
            execution_checks.get("secrets_absent_from_repo") is True
            and execution.get("secrets_present_in_repo") is False
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    ready = not failed
    return {
        "version": "v204_btcusdc_real_money_readiness_gate",
        "config": {
            "min_forward_trades": MIN_FORWARD_TRADES,
            "max_execution_slippage_bps_p95": MAX_EXECUTION_SLIPPAGE_BPS_P95,
            "min_execution_fills": MIN_EXECUTION_FILLS,
            "requires_clean_overfit_audit": True,
            "requires_forward_evidence": True,
            "requires_forward_freshness": True,
            "requires_public_data_availability": True,
            "requires_realtime_smoke_clean": True,
            "requires_execution_validation": True,
            "requires_execution_provenance": True,
            "requires_signal_provenance": True,
            "requires_readiness_source_provenance": True,
            "requires_readiness_input_hashes": True,
            "changes_strategy_thresholds": False,
            "changes_trade_side": False,
            "changes_leverage_logic": False,
        },
        "inputs": inputs,
        "evidence": {
            "overfit_status": overfit.get("status", "missing"),
            "stop_historical_optimization": overfit.get("stop_historical_optimization"),
            "forward_status": forward.get("status", "missing"),
            "forward_evidence_available": forward.get("forward_evidence_available"),
            "forward_trade_count": int(forward.get("forward_trade_count", 0) or 0),
            "forward_freshness_status": forward_freshness.get("status", "missing"),
            "forward_data_current": forward_freshness.get("forward_data_current"),
            "fresh_forward_evidence_available": forward_freshness.get("forward_evidence_available"),
            "public_data_status": public_data.get("status", "missing"),
            "public_data_available": public_data.get("public_data_available"),
            "public_data_failed_checks": public_data.get("failed_checks", []),
            "rejected_signals": int(realtime.get("rejected_signals", 0) or 0),
            "market_data_errors": int(realtime.get("market_data_errors", 0) or 0),
            "execution_status": execution.get("status", "missing"),
            "execution_failed_checks": execution.get("failed_checks", []),
            "execution_validation_passed": execution.get("execution_validation_passed"),
            "execution_fill_count": int(execution_evidence.get("fill_count", 0) or 0),
            "kill_switch_tested": execution.get("kill_switch_tested"),
            "secrets_present_in_repo": execution.get("secrets_present_in_repo"),
            "max_slippage_bps_p95": execution.get("max_slippage_bps_p95"),
            "execution_fill_evidence_available": execution_checks.get("fill_evidence_available"),
            "filled_status_clean": execution_checks.get("filled_status_clean"),
            "execution_provenance_clean": execution_checks.get("execution_provenance_clean"),
            "signal_provenance_clean": execution_checks.get("signal_provenance_clean"),
            "execution_slippage_p95_clean": execution_checks.get("slippage_p95_clean"),
            "execution_kill_switch_tested": execution_checks.get("kill_switch_tested"),
            "execution_secrets_absent_from_repo": execution_checks.get("secrets_absent_from_repo"),
            "readiness_source_commit": source_commit,
            "readiness_runtime_source_clean": readiness_source_clean,
            "readiness_dirty_runtime_paths": dirty_paths,
            "readiness_dirty_runtime_path_count": len(dirty_paths),
            "readiness_input_hashes": input_hashes,
        },
        "checks": checks,
        "decision": {
            "status": "real_money_ready" if ready else "real_money_blocked",
            "promote_to_real_money": ready,
            "failed_checks": failed,
            "message": (
                "All real-money readiness gates passed."
                if ready
                else "Do not use with real money. The failed checks must be resolved with new evidence first."
            ),
        },
    }


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_report(payload: dict[str, Any]) -> None:
    decision = payload["decision"]
    evidence = payload["evidence"]
    checks = payload["checks"]
    lines = [
        "# Research V204 BTCUSDC Real-Money Readiness Gate",
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
        f"| Readiness source provenance clean | {checks['readiness_source_provenance_clean']} | source_commit={evidence['readiness_source_commit']}; dirty_runtime_path_count={evidence['readiness_dirty_runtime_path_count']} |",
        f"| Readiness input hashes clean | {checks['readiness_input_hashes_clean']} | input_hash_count={len(evidence['readiness_input_hashes'])} |",
        f"| Historical optimization clean | {checks['historical_optimization_frozen_clean']} | overfit_status={evidence['overfit_status']}; stop_historical_optimization={evidence['stop_historical_optimization']} |",
        f"| Forward evidence available | {checks['forward_evidence_available']} | forward_status={evidence['forward_status']}; forward_trade_count={evidence['forward_trade_count']} |",
        f"| Forward freshness clean | {checks['forward_freshness_clean']} | forward_freshness_status={evidence['forward_freshness_status']}; forward_data_current={evidence['forward_data_current']}; fresh_forward_evidence_available={evidence['fresh_forward_evidence_available']} |",
        f"| Public data available | {checks['public_data_available']} | public_data_status={evidence['public_data_status']}; public_data_available={evidence['public_data_available']}; failed_checks={evidence['public_data_failed_checks']} |",
        f"| Realtime smoke clean | {checks['realtime_smoke_clean']} | rejected_signals={evidence['rejected_signals']}; market_data_errors={evidence['market_data_errors']} |",
        f"| Execution validation passed | {checks['execution_validation_passed']} | execution_status={evidence['execution_status']}; execution_validation_passed={evidence['execution_validation_passed']}; failed_checks={evidence['execution_failed_checks']} |",
        f"| Execution fill evidence available | {checks['execution_fill_evidence_available']} | fill_count={evidence['execution_fill_count']}; min_execution_fills={payload['config']['min_execution_fills']} |",
        f"| Filled status clean | {checks['filled_status_clean']} | filled_status_clean={evidence['filled_status_clean']} |",
        f"| Execution provenance clean | {checks['execution_provenance_clean']} | execution_provenance_clean={evidence['execution_provenance_clean']} |",
        f"| Signal provenance clean | {checks['signal_provenance_clean']} | signal_provenance_clean={evidence['signal_provenance_clean']} |",
        f"| Execution slippage p95 clean | {checks['execution_slippage_p95_clean']} | max_slippage_bps_p95={evidence['max_slippage_bps_p95']}; slippage_p95_clean={evidence['execution_slippage_p95_clean']} |",
        f"| Execution kill switch tested | {checks['execution_kill_switch_tested']} | kill_switch_tested={evidence['kill_switch_tested']}; execution_check={evidence['execution_kill_switch_tested']} |",
        f"| Execution secrets absent | {checks['execution_secrets_absent_from_repo']} | secrets_present_in_repo={evidence['secrets_present_in_repo']}; execution_check={evidence['execution_secrets_absent_from_repo']} |",
        "",
        "## Iteration Metrics",
        "",
        "| Metric | V204 |",
        "|---|---:|",
        "| Strategy thresholds changed | No |",
        "| Entry/exit logic changed | No |",
        "| Leverage logic changed | No |",
        f"| New real-money readiness gate | {True} |",
        f"| Promote to real money | {decision['promote_to_real_money']} |",
        "",
        "## Interpretation",
        "",
        "V204 is an admission gate, not a new trading strategy. It blocks real-money use when source provenance is missing, input evidence hashes are missing, historical overfitting risk, missing forward evidence, missing forward freshness, incomplete public data, realtime smoke errors, missing execution validation, or missing execution/signal provenance are present.",
        "",
        "This remains research and safety infrastructure until all gates pass with current evidence.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    inputs = {
        "overfit_audit": str(V195_SUMMARY),
        "forward_monitoring": str(V196_SUMMARY),
        "forward_freshness": str(V212_SUMMARY),
        "public_data_availability": str(V214_SUMMARY),
        "realtime_smoke": str(REALTIME_SMOKE_SUMMARY),
        "execution_validation": str(EXECUTION_VALIDATION_SUMMARY),
    }
    payload = _payload_for_readiness(
        overfit_payload=_load_json(V195_SUMMARY),
        forward_payload=_load_json(V196_SUMMARY),
        realtime_summary=_load_json(REALTIME_SMOKE_SUMMARY),
        execution_payload=_load_json(EXECUTION_VALIDATION_SUMMARY),
        forward_freshness_payload=_load_json(V212_SUMMARY),
        public_data_payload=_load_json(V214_SUMMARY),
        source_commit=_current_git_commit(),
        dirty_runtime_paths=_dirty_runtime_paths_from_git(),
        readiness_input_hashes=_readiness_input_hashes(inputs),
    )
    (OUT_DIR / "v204_real_money_readiness_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
