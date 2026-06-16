from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v212_forward_freshness_gate"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V212_BTCUSDC_FORWARD_FRESHNESS_GATE.md"
V90_SUMMARY = ROOT / "runs" / "research_v90_btcusdc_forward_monitoring" / "v90_summary.json"
AGGTRADE_DIR = ROOT / "data" / "binance_public" / "um" / "daily" / "aggTrades" / "BTCUSDC"
MIN_FORWARD_TRADES = 30


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _date_from_aggtrade_path(path: Path) -> date | None:
    parts = path.stem.rsplit("-", 3)[-3:]
    if len(parts) != 3:
        return None
    try:
        return date.fromisoformat("-".join(parts))
    except ValueError:
        return None


def _latest_local_public_file_date(path: Path = AGGTRADE_DIR) -> str | None:
    days = [_date_from_aggtrade_path(item) for item in path.glob("BTCUSDC-aggTrades-*.zip")]
    clean = [day for day in days if day is not None]
    return max(clean).isoformat() if clean else None


def _combined_end_date(v90_payload: dict[str, Any] | None) -> str | None:
    if not isinstance(v90_payload, dict):
        return None
    data = v90_payload.get("data", {})
    if not isinstance(data, dict):
        return None
    combined_end = data.get("combined_end")
    if not combined_end:
        return None
    try:
        return pd.Timestamp(str(combined_end)).date().isoformat()
    except ValueError:
        return None


def _decision(v90_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(v90_payload, dict):
        return {}
    decision = v90_payload.get("decision", {})
    return decision if isinstance(decision, dict) else {}


def _payload_for_forward_freshness(
    *,
    v90_payload: dict[str, Any] | None,
    latest_public_file_date: str | None,
    min_forward_trades: int = MIN_FORWARD_TRADES,
) -> dict[str, Any]:
    decision = _decision(v90_payload)
    combined_end_date = _combined_end_date(v90_payload)
    v90_status = str(decision.get("status", "missing"))
    forward_signal_count = int(decision.get("new_signal_count", 0) or 0)
    data_current = bool(combined_end_date and latest_public_file_date and combined_end_date >= latest_public_file_date)
    enough_forward_signals = forward_signal_count >= int(min_forward_trades)
    v90_passed = v90_status == "passed"
    forward_evidence_available = bool(data_current and enough_forward_signals and v90_passed)

    checks = {
        "v90_summary_available": isinstance(v90_payload, dict),
        "latest_public_file_available": latest_public_file_date is not None,
        "forward_data_current": data_current,
        "forward_evidence_available": forward_evidence_available,
    }
    failed = [name for name, passed in checks.items() if not passed]

    if not checks["v90_summary_available"]:
        status = "forward_freshness_missing_summary"
    elif not checks["latest_public_file_available"]:
        status = "forward_freshness_missing_public_data"
    elif not data_current:
        status = "forward_freshness_stale"
    elif forward_signal_count == 0:
        status = "forward_fresh_no_signal"
    elif not v90_passed:
        status = "forward_monitoring_failed"
    elif not enough_forward_signals:
        status = "forward_evidence_insufficient"
    else:
        status = "forward_freshness_passed"

    return {
        "version": "v212_btcusdc_forward_freshness_gate",
        "config": {
            "source": "v90_btcusdc_forward_monitoring",
            "min_forward_trades": int(min_forward_trades),
            "changes_strategy_thresholds": False,
            "changes_trade_side": False,
            "changes_leverage_logic": False,
            "places_live_orders": False,
            "promotes_real_money": False,
        },
        "evidence": {
            "v90_status": v90_status,
            "v90_combined_end_date": combined_end_date,
            "latest_public_file_date": latest_public_file_date,
            "forward_signal_count": forward_signal_count,
        },
        "checks": checks,
        "decision": {
            "status": status,
            "forward_data_current": data_current,
            "forward_evidence_available": forward_evidence_available,
            "promote_to_real_money": False,
            "failed_checks": failed,
            "message": (
                "Current forward data has enough passing forward evidence."
                if forward_evidence_available
                else "Do not use with real money. Current forward monitoring evidence is missing, stale, failed, or has no enough trades."
            ),
        },
    }


def _write_report(payload: dict[str, Any]) -> None:
    decision = payload["decision"]
    evidence = payload["evidence"]
    checks = payload["checks"]
    lines = [
        "# Research V212 BTCUSDC Forward Freshness Gate",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Forward data current: `{decision['forward_data_current']}`",
        f"- Forward evidence available: `{decision['forward_evidence_available']}`",
        f"- Promote to real money: `{decision['promote_to_real_money']}`",
        f"- Failed checks: `{', '.join(decision['failed_checks']) if decision['failed_checks'] else 'none'}`",
        f"- Message: {decision['message']}",
        "",
        "## Gate Checks",
        "",
        "| Check | Passed | Evidence |",
        "|---|---:|---|",
        f"| V90 summary available | {checks['v90_summary_available']} | v90_status={evidence['v90_status']} |",
        f"| Latest public file available | {checks['latest_public_file_available']} | latest_public_file_date={evidence['latest_public_file_date']} |",
        f"| Forward data current | {checks['forward_data_current']} | v90_combined_end_date={evidence['v90_combined_end_date']}; latest_public_file_date={evidence['latest_public_file_date']} |",
        f"| Forward evidence available | {checks['forward_evidence_available']} | forward_signal_count={evidence['forward_signal_count']} |",
        "",
        "## Iteration Metrics",
        "",
        "| Metric | V212 |",
        "|---|---:|",
        "| Strategy thresholds changed | No |",
        "| Entry/exit logic changed | No |",
        "| Leverage logic changed | No |",
        "| New backtest return improvement claimed | No |",
        "| Places live orders | No |",
        f"| Forward data current | {decision['forward_data_current']} |",
        f"| Forward evidence available | {decision['forward_evidence_available']} |",
        f"| Promote to real money | {decision['promote_to_real_money']} |",
        "",
        "## Interpretation",
        "",
        "V212 prevents a current no-signal V90 run or a stale V90 run from being treated as real-money forward validation. It only evaluates evidence freshness and signal availability.",
        "",
        "This does not create trades, tune thresholds, or claim new profitability. Real-money use remains blocked until the full readiness gate passes with current forward and execution evidence.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = _payload_for_forward_freshness(
        v90_payload=_load_json(V90_SUMMARY),
        latest_public_file_date=_latest_local_public_file_date(),
    )
    (OUT_DIR / "v212_forward_freshness_gate_summary.json").write_text(
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
