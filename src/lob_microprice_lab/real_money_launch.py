from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
READINESS_SUMMARY = ROOT / "runs" / "research_v204_real_money_readiness_gate" / "v204_real_money_readiness_summary.json"
REQUIRED_ARM_TOKEN = "I_UNDERSTAND_THIS_USES_REAL_MONEY"
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


def _readiness_forward_freshness_clean(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    config = payload.get("config", {})
    checks = payload.get("checks", {})
    evidence = payload.get("evidence", {})
    return (
        isinstance(config, dict)
        and isinstance(checks, dict)
        and isinstance(evidence, dict)
        and config.get("requires_forward_freshness") is True
        and checks.get("forward_freshness_clean") is True
        and evidence.get("forward_freshness_status") == "forward_freshness_passed"
        and evidence.get("forward_data_current") is True
        and evidence.get("fresh_forward_evidence_available") is True
    )


def _readiness_public_data_available(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    config = payload.get("config", {})
    checks = payload.get("checks", {})
    evidence = payload.get("evidence", {})
    return (
        isinstance(config, dict)
        and isinstance(checks, dict)
        and isinstance(evidence, dict)
        and config.get("requires_public_data_availability") is True
        and checks.get("public_data_available") is True
        and evidence.get("public_data_status") == "public_data_availability_passed"
        and evidence.get("public_data_available") is True
    )


def _readiness_execution_provenance_clean(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    config = payload.get("config", {})
    checks = payload.get("checks", {})
    evidence = payload.get("evidence", {})
    if not (isinstance(config, dict) and isinstance(checks, dict) and isinstance(evidence, dict)):
        return False
    min_execution_fills = int(config.get("min_execution_fills", 0) or 0)
    execution_fill_count = int(evidence.get("execution_fill_count", 0) or 0)
    required_checks = (
        "execution_validation_passed",
        "execution_fill_evidence_available",
        "filled_status_clean",
        "execution_provenance_clean",
        "signal_provenance_clean",
        "execution_slippage_p95_clean",
        "execution_kill_switch_tested",
        "execution_secrets_absent_from_repo",
    )
    required_evidence = (
        "execution_validation_passed",
        "execution_fill_evidence_available",
        "filled_status_clean",
        "execution_provenance_clean",
        "signal_provenance_clean",
        "execution_slippage_p95_clean",
        "execution_kill_switch_tested",
        "execution_secrets_absent_from_repo",
    )
    return (
        config.get("requires_execution_validation") is True
        and config.get("requires_execution_provenance") is True
        and config.get("requires_signal_provenance") is True
        and min_execution_fills > 0
        and execution_fill_count >= min_execution_fills
        and all(checks.get(name) is True for name in required_checks)
        and all(evidence.get(name) is True for name in required_evidence)
    )


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


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


def real_money_launch_preflight(
    *,
    out_dir: str | Path,
    arm_token: str,
    readiness_summary: Path = READINESS_SUMMARY,
) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    readiness_payload = _load_json(readiness_summary)
    readiness = _decision(readiness_payload)
    forward_freshness_clean = _readiness_forward_freshness_clean(readiness_payload)
    public_data_available = _readiness_public_data_available(readiness_payload)
    execution_provenance_clean = _readiness_execution_provenance_clean(readiness_payload)
    dirty_runtime_paths = _dirty_runtime_paths_from_git()
    checks = {
        "readiness_gate_passed": (
            readiness.get("status") == "real_money_ready"
            and readiness.get("promote_to_real_money") is True
            and not readiness.get("failed_checks")
        ),
        "readiness_forward_freshness_clean": forward_freshness_clean,
        "readiness_public_data_available": public_data_available,
        "readiness_execution_provenance_clean": execution_provenance_clean,
        "explicit_real_money_arm": arm_token == REQUIRED_ARM_TOKEN,
        "runtime_source_clean": len(dirty_runtime_paths) == 0,
    }
    failed = [name for name, passed in checks.items() if not passed]
    allowed = not failed
    payload = {
        "version": "v207_real_trade_btcusdc_cli_preflight",
        "config": {
            "required_arm_token": REQUIRED_ARM_TOKEN,
            "places_live_orders": False,
            "changes_strategy_thresholds": False,
            "changes_trade_side": False,
            "changes_leverage_logic": False,
            "requires_v204_readiness": True,
            "requires_v212_forward_freshness": True,
            "requires_v214_public_data_availability": True,
            "requires_v216_execution_provenance": True,
            "requires_explicit_arm": True,
            "requires_clean_runtime_source": True,
        },
        "evidence": {
            "readiness_summary": str(readiness_summary),
            "readiness_status": readiness.get("status", "missing"),
            "readiness_promote_to_real_money": readiness.get("promote_to_real_money"),
            "readiness_failed_checks": readiness.get("failed_checks", []),
            "readiness_forward_freshness_clean": forward_freshness_clean,
            "readiness_public_data_available": public_data_available,
            "readiness_execution_provenance_clean": execution_provenance_clean,
            "dirty_runtime_paths": dirty_runtime_paths,
            "dirty_runtime_path_count": len(dirty_runtime_paths),
        },
        "checks": checks,
        "decision": {
            "status": "real_money_cli_preflight_passed" if allowed else "real_money_cli_blocked",
            "allow_real_money_launch": allowed,
            "failed_checks": failed,
            "message": (
                "Real-money CLI preflight passed. This command still does not place live orders."
                if allowed
                else "Do not launch real-money trading. CLI preflight checks failed."
            ),
        },
    }
    (out / "real_money_launch_preflight_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return payload
