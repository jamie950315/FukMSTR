from __future__ import annotations

import argparse
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
) -> dict[str, Any]:
    readiness = _decision(readiness_payload)
    checks = {
        "readiness_gate_passed": (
            readiness.get("status") == "real_money_ready"
            and readiness.get("promote_to_real_money") is True
            and not readiness.get("failed_checks")
        ),
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
            "requires_explicit_arm": True,
            "requires_clean_runtime_source": True,
        },
        "evidence": {
            "readiness_status": readiness.get("status", "missing"),
            "readiness_promote_to_real_money": readiness.get("promote_to_real_money"),
            "readiness_failed_checks": readiness.get("failed_checks", []),
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
        "V206 is a final launch preflight. It prevents any real-money path from being treated as launchable unless V204 is already ready, the operator explicitly arms real-money mode, and runtime source files are clean.",
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
