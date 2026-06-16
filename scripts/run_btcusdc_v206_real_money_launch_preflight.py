from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v206_real_money_launch_preflight"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V206_BTCUSDC_REAL_MONEY_LAUNCH_PREFLIGHT.md"
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
        "recent_execution_evidence_clean",
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
        "recent_execution_evidence_clean",
        "execution_kill_switch_tested",
        "execution_secrets_absent_from_repo",
    )
    return (
        config.get("requires_execution_validation") is True
        and config.get("requires_execution_provenance") is True
        and config.get("requires_signal_provenance") is True
        and config.get("requires_recent_execution_evidence") is True
        and min_execution_fills > 0
        and execution_fill_count >= min_execution_fills
        and all(checks.get(name) is True for name in required_checks)
        and all(evidence.get(name) is True for name in required_evidence)
    )


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


def _runtime_source_hash_from_git() -> str:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "runtime_source_hash_unavailable"
    digest = hashlib.sha256()
    count = 0
    for rel_path in sorted(line for line in result.stdout.splitlines() if line):
        if not (rel_path.startswith(RUNTIME_PREFIXES) or rel_path in RUNTIME_PREFIXES):
            continue
        path = ROOT / rel_path
        if not path.is_file():
            continue
        digest.update(rel_path.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        count += 1
    if count == 0:
        return "runtime_source_hash_unavailable"
    return digest.hexdigest()


def _source_commit_is_ancestor(source_commit: str, current_source_commit: str) -> bool:
    if source_commit in {"", "git_commit_unavailable"} or current_source_commit in {"", "git_commit_unavailable"}:
        return False
    if source_commit == current_source_commit:
        return True
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", source_commit, current_source_commit],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return result.returncode == 0


def _readiness_source_provenance_clean(
    payload: dict[str, Any] | None,
    *,
    current_source_commit: str,
    current_runtime_source_hash: str,
    readiness_source_commit_is_ancestor: bool | None = None,
) -> bool:
    if not isinstance(payload, dict):
        return False
    config = payload.get("config", {})
    checks = payload.get("checks", {})
    evidence = payload.get("evidence", {})
    if not (isinstance(config, dict) and isinstance(checks, dict) and isinstance(evidence, dict)):
        return False
    dirty_path_count = evidence.get("readiness_dirty_runtime_path_count", 999)
    if dirty_path_count is None:
        dirty_path_count = 999
    source_commit = str(evidence.get("readiness_source_commit", ""))
    source_ancestor = (
        _source_commit_is_ancestor(source_commit, current_source_commit)
        if readiness_source_commit_is_ancestor is None
        else readiness_source_commit_is_ancestor
    )
    base_clean = (
        current_source_commit not in {"", "git_commit_unavailable"}
        and current_runtime_source_hash not in {"", "runtime_source_hash_unavailable"}
        and config.get("requires_readiness_source_provenance") is True
        and config.get("requires_readiness_runtime_source_hash") is True
        and checks.get("readiness_source_provenance_clean") is True
        and checks.get("readiness_runtime_source_hash_clean") is True
        and int(dirty_path_count) == 0
        and evidence.get("readiness_runtime_source_clean") is True
    )
    source_commit_clean = source_commit == current_source_commit or source_ancestor
    runtime_hash_clean = evidence.get("readiness_runtime_source_hash") == current_runtime_source_hash
    return bool(
        base_clean
        and source_commit_clean
        and runtime_hash_clean
    )


def _file_sha256(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return "missing"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _readiness_input_hashes_clean(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    config = payload.get("config", {})
    checks = payload.get("checks", {})
    inputs = payload.get("inputs", {})
    evidence = payload.get("evidence", {})
    if not (
        isinstance(config, dict)
        and isinstance(checks, dict)
        and isinstance(inputs, dict)
        and isinstance(evidence, dict)
    ):
        return False
    expected_hashes = evidence.get("readiness_input_hashes", {})
    if not isinstance(expected_hashes, dict) or not expected_hashes:
        return False
    if set(expected_hashes) != set(inputs):
        return False
    current_hashes = {name: _file_sha256(Path(str(path))) for name, path in inputs.items()}
    return (
        config.get("requires_readiness_input_hashes") is True
        and checks.get("readiness_input_hashes_clean") is True
        and all(value not in {"", "missing"} for value in expected_hashes.values())
        and current_hashes == expected_hashes
    )


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


def _preflight_payload(
    *,
    readiness_payload: dict[str, Any] | None,
    arm_token: str,
    dirty_runtime_paths: list[str],
    current_source_commit: str = "test-source-commit",
    current_runtime_source_hash: str = "runtime-source-hash",
    readiness_source_commit_is_ancestor: bool | None = None,
) -> dict[str, Any]:
    readiness = _decision(readiness_payload)
    forward_freshness_clean = _readiness_forward_freshness_clean(readiness_payload)
    public_data_available = _readiness_public_data_available(readiness_payload)
    execution_provenance_clean = _readiness_execution_provenance_clean(readiness_payload)
    source_provenance_clean = _readiness_source_provenance_clean(
        readiness_payload,
        current_source_commit=current_source_commit,
        current_runtime_source_hash=current_runtime_source_hash,
        readiness_source_commit_is_ancestor=readiness_source_commit_is_ancestor,
    )
    input_hashes_clean = _readiness_input_hashes_clean(readiness_payload)
    checks = {
        "readiness_gate_passed": (
            readiness.get("status") == "real_money_ready"
            and readiness.get("promote_to_real_money") is True
            and not readiness.get("failed_checks")
        ),
        "readiness_forward_freshness_clean": forward_freshness_clean,
        "readiness_public_data_available": public_data_available,
        "readiness_execution_provenance_clean": execution_provenance_clean,
        "readiness_source_provenance_clean": source_provenance_clean,
        "readiness_input_hashes_clean": input_hashes_clean,
        "explicit_real_money_arm": arm_token == REQUIRED_ARM_TOKEN,
        "runtime_source_clean": len(dirty_runtime_paths) == 0,
    }
    failed = [name for name, passed in checks.items() if not passed]
    allowed = not failed
    return {
        "version": "v206_btcusdc_real_money_launch_preflight",
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
            "requires_v218_readiness_source_provenance": True,
            "requires_v219_readiness_input_hashes": True,
            "requires_v220_recent_execution_evidence": True,
            "requires_v221_runtime_source_hash": True,
            "requires_explicit_arm": True,
            "requires_clean_runtime_source": True,
        },
        "evidence": {
            "readiness_status": readiness.get("status", "missing"),
            "readiness_promote_to_real_money": readiness.get("promote_to_real_money"),
            "readiness_failed_checks": readiness.get("failed_checks", []),
            "readiness_forward_freshness_clean": forward_freshness_clean,
            "readiness_public_data_available": public_data_available,
            "readiness_execution_provenance_clean": execution_provenance_clean,
            "readiness_source_provenance_clean": source_provenance_clean,
            "readiness_input_hashes_clean": input_hashes_clean,
            "current_source_commit": current_source_commit,
            "current_runtime_source_hash": current_runtime_source_hash,
            "dirty_runtime_paths": dirty_runtime_paths,
            "dirty_runtime_path_count": len(dirty_runtime_paths),
        },
        "checks": checks,
        "decision": {
            "status": "real_money_launch_preflight_passed" if allowed else "real_money_launch_blocked",
            "allow_real_money_launch": allowed,
            "failed_checks": failed,
            "message": (
                "Real-money launch preflight passed. This script still does not place live orders."
                if allowed
                else "Do not launch real-money trading. Preflight checks failed."
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
        "# Research V206 BTCUSDC Real-Money Launch Preflight",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Allow real-money launch: `{decision['allow_real_money_launch']}`",
        f"- Failed checks: `{', '.join(decision['failed_checks']) if decision['failed_checks'] else 'none'}`",
        f"- Message: {decision['message']}",
        "",
        "## Gate Checks",
        "",
        "| Check | Passed | Evidence |",
        "|---|---:|---|",
        f"| V204 readiness gate passed | {checks['readiness_gate_passed']} | status={evidence['readiness_status']}; promote_to_real_money={evidence['readiness_promote_to_real_money']}; failed_checks={evidence['readiness_failed_checks']} |",
        f"| V212 forward freshness present and passed | {checks['readiness_forward_freshness_clean']} | readiness_forward_freshness_clean={evidence['readiness_forward_freshness_clean']} |",
        f"| V214 public data present and passed | {checks['readiness_public_data_available']} | readiness_public_data_available={evidence['readiness_public_data_available']} |",
        f"| V216 execution provenance present and passed | {checks['readiness_execution_provenance_clean']} | readiness_execution_provenance_clean={evidence['readiness_execution_provenance_clean']} |",
        f"| V218/V221 readiness source provenance present and current | {checks['readiness_source_provenance_clean']} | readiness_source_provenance_clean={evidence['readiness_source_provenance_clean']}; current_source_commit={evidence['current_source_commit']}; current_runtime_source_hash={evidence['current_runtime_source_hash']} |",
        f"| V219 readiness input hashes present and current | {checks['readiness_input_hashes_clean']} | readiness_input_hashes_clean={evidence['readiness_input_hashes_clean']} |",
        f"| V220 recent execution evidence present and current | {checks['readiness_execution_provenance_clean']} | included in readiness_execution_provenance_clean |",
        f"| Explicit real-money arm | {checks['explicit_real_money_arm']} | required token is documented but not persisted |",
        f"| Runtime source clean | {checks['runtime_source_clean']} | dirty_runtime_path_count={evidence['dirty_runtime_path_count']} |",
        "",
        "## Dirty Runtime Paths",
        "",
        "\n".join(f"- `{path}`" for path in evidence["dirty_runtime_paths"]) or "none",
        "",
        "## Iteration Metrics",
        "",
        "| Metric | V206 |",
        "|---|---:|",
        "| Strategy thresholds changed | No |",
        "| Entry/exit logic changed | No |",
        "| Leverage logic changed | No |",
        "| Places live orders | No |",
        f"| Allow real-money launch | {decision['allow_real_money_launch']} |",
        "",
        "## Interpretation",
        "",
        "V206 is a final launch preflight. It prevents any real-money path from being treated as launchable unless V204 is already ready with V212 forward freshness evidence, V214 public-data evidence, V216 execution/signal provenance evidence, V218/V221 current runtime-source provenance evidence, V219 current input evidence hashes, and V220 recent execution evidence, the operator explicitly arms real-money mode, and runtime source files are clean.",
        "",
        "This is still not live trading code and it does not place exchange orders.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run(*, arm_token: str = "") -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = _preflight_payload(
        readiness_payload=_load_json(READINESS_SUMMARY),
        arm_token=arm_token,
        dirty_runtime_paths=_dirty_runtime_paths_from_git(),
        current_source_commit=_current_git_commit(),
        current_runtime_source_hash=_runtime_source_hash_from_git(),
    )
    (OUT_DIR / "v206_real_money_launch_preflight_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the BTCUSDC real-money launch preflight.")
    parser.add_argument("--arm-real-money-token", default="")
    args = parser.parse_args()
    payload = run(arm_token=args.arm_real_money_token)
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
