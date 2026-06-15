from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v204_real_money_readiness_gate"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V204_BTCUSDC_REAL_MONEY_READINESS_GATE.md"
V195_SUMMARY = ROOT / "runs" / "research_v195_post_goal_overfitting_audit" / "v195_post_goal_overfitting_audit_summary.json"
V196_SUMMARY = ROOT / "runs" / "research_v196_forward_monitoring_gate" / "v196_forward_monitoring_gate_summary.json"
REALTIME_SMOKE_SUMMARY = ROOT / "runs" / "paper_v142_realtime_safe_smoke" / "summary.json"
EXECUTION_VALIDATION_SUMMARY = (
    ROOT / "runs" / "research_v204_real_money_execution_validation" / "execution_validation_summary.json"
)

MIN_FORWARD_TRADES = 30
MAX_EXECUTION_SLIPPAGE_BPS_P95 = 5.0


def _decision(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    decision = payload.get("decision", {})
    return decision if isinstance(decision, dict) else {}


def _payload_for_readiness(
    *,
    overfit_payload: dict[str, Any] | None,
    forward_payload: dict[str, Any] | None,
    realtime_summary: dict[str, Any] | None,
    execution_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    overfit = _decision(overfit_payload)
    forward = _decision(forward_payload)
    execution = _decision(execution_payload)
    realtime = realtime_summary if isinstance(realtime_summary, dict) else {}

    checks = {
        "historical_optimization_frozen_clean": (
            overfit.get("status") == "post_goal_overfitting_not_detected"
            and overfit.get("stop_historical_optimization") is False
        ),
        "forward_evidence_available": (
            forward.get("forward_evidence_available") is True
            and int(forward.get("forward_trade_count", 0) or 0) >= MIN_FORWARD_TRADES
        ),
        "realtime_smoke_clean": (
            int(realtime.get("rejected_signals", 0) or 0) == 0
            and int(realtime.get("market_data_errors", 0) or 0) == 0
        ),
        "execution_validation_passed": (
            execution.get("status") == "execution_validation_passed"
            and execution.get("kill_switch_tested") is True
            and execution.get("secrets_present_in_repo") is False
            and float(execution.get("max_slippage_bps_p95", 999.0) or 999.0) <= MAX_EXECUTION_SLIPPAGE_BPS_P95
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    ready = not failed
    return {
        "version": "v204_btcusdc_real_money_readiness_gate",
        "config": {
            "min_forward_trades": MIN_FORWARD_TRADES,
            "max_execution_slippage_bps_p95": MAX_EXECUTION_SLIPPAGE_BPS_P95,
            "requires_clean_overfit_audit": True,
            "requires_forward_evidence": True,
            "requires_realtime_smoke_clean": True,
            "requires_execution_validation": True,
            "changes_strategy_thresholds": False,
            "changes_trade_side": False,
            "changes_leverage_logic": False,
        },
        "inputs": {
            "overfit_audit": str(V195_SUMMARY),
            "forward_monitoring": str(V196_SUMMARY),
            "realtime_smoke": str(REALTIME_SMOKE_SUMMARY),
            "execution_validation": str(EXECUTION_VALIDATION_SUMMARY),
        },
        "evidence": {
            "overfit_status": overfit.get("status", "missing"),
            "stop_historical_optimization": overfit.get("stop_historical_optimization"),
            "forward_status": forward.get("status", "missing"),
            "forward_evidence_available": forward.get("forward_evidence_available"),
            "forward_trade_count": int(forward.get("forward_trade_count", 0) or 0),
            "rejected_signals": int(realtime.get("rejected_signals", 0) or 0),
            "market_data_errors": int(realtime.get("market_data_errors", 0) or 0),
            "execution_status": execution.get("status", "missing"),
            "kill_switch_tested": execution.get("kill_switch_tested"),
            "secrets_present_in_repo": execution.get("secrets_present_in_repo"),
            "max_slippage_bps_p95": execution.get("max_slippage_bps_p95"),
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
        f"| Historical optimization clean | {checks['historical_optimization_frozen_clean']} | overfit_status={evidence['overfit_status']}; stop_historical_optimization={evidence['stop_historical_optimization']} |",
        f"| Forward evidence available | {checks['forward_evidence_available']} | forward_status={evidence['forward_status']}; forward_trade_count={evidence['forward_trade_count']} |",
        f"| Realtime smoke clean | {checks['realtime_smoke_clean']} | rejected_signals={evidence['rejected_signals']}; market_data_errors={evidence['market_data_errors']} |",
        f"| Execution validation passed | {checks['execution_validation_passed']} | execution_status={evidence['execution_status']}; kill_switch_tested={evidence['kill_switch_tested']}; secrets_present_in_repo={evidence['secrets_present_in_repo']}; max_slippage_bps_p95={evidence['max_slippage_bps_p95']} |",
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
        "V204 is an admission gate, not a new trading strategy. It blocks real-money use when historical overfitting risk, missing forward evidence, realtime smoke errors, or missing execution validation are present.",
        "",
        "This remains research and safety infrastructure until all gates pass with current evidence.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = _payload_for_readiness(
        overfit_payload=_load_json(V195_SUMMARY),
        forward_payload=_load_json(V196_SUMMARY),
        realtime_summary=_load_json(REALTIME_SMOKE_SUMMARY),
        execution_payload=_load_json(EXECUTION_VALIDATION_SUMMARY),
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
