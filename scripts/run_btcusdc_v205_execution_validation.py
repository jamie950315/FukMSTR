from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import UTC
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v204_real_money_execution_validation"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V205_BTCUSDC_EXECUTION_VALIDATION.md"
DEFAULT_FILLS = ROOT / "runs" / "research_v205_execution_validation" / "fill_audit.csv"
DEFAULT_KILL_SWITCH_EVENTS = ROOT / "runs" / "research_v205_execution_validation" / "kill_switch_events.csv"

MIN_EXECUTION_FILLS = 30
MAX_SLIPPAGE_BPS_P95 = 5.0
MAX_EXECUTION_EVIDENCE_AGE_DAYS = 7
BASE_FILL_COLUMNS = {"timestamp", "symbol", "side", "intended_price", "fill_price", "status"}
PROVENANCE_FILL_COLUMNS = {
    "venue",
    "execution_mode",
    "evidence_source",
    "capture_id",
    "order_id",
    "client_order_id",
    "exchange_timestamp",
}
SIGNAL_PROVENANCE_COLUMNS = {"signal_id", "signal_source", "market_source"}
ALLOWED_EXECUTION_MODES = {"paper_shadow_live", "exchange_testnet", "exchange_live_min_size"}
BLOCKED_EVIDENCE_SOURCES = {"", "unknown", "synthetic", "backtest", "manual"}
BLOCKED_SIGNAL_SOURCES = {"", "unknown", "synthetic", "backtest", "manual"}
BLOCKED_MARKET_SOURCES = {"", "unknown", "synthetic", "backtest", "manual"}
SECRET_ASSIGNMENT = re.compile(
    r"(?i)\\b(binance(_api)?_(key|secret)|api[_-]?secret|secret[_-]?key|private[_-]?key|aws_secret_access_key)\\b\\s*[:=]\\s*['\\\"]?([^'\\\"\\s#]+)"
)
PLACEHOLDER_VALUES = {
    "",
    "changeme",
    "example",
    "placeholder",
    "redacted",
    "your_key_here",
    "your_secret_here",
    "<redacted>",
}


def _read_csv_or_empty(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _slippage_bps(fills: pd.DataFrame) -> pd.Series:
    intended = pd.to_numeric(fills.get("intended_price"), errors="coerce")
    filled = pd.to_numeric(fills.get("fill_price"), errors="coerce")
    return ((filled - intended).abs() / intended.abs() * 10_000.0).replace([float("inf"), -float("inf")], pd.NA)


def _kill_switch_tested(events: pd.DataFrame) -> bool:
    if events.empty or "event_type" not in events.columns:
        return False
    event_types = events["event_type"].astype(str).str.strip().str.lower()
    return bool(event_types.eq("kill_switch_tested").any())


def _non_empty_string_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([False] * len(frame), index=frame.index)
    return frame[column].astype(str).str.strip().ne("") & frame[column].notna()


def _execution_provenance_clean(fills: pd.DataFrame, *, fill_evidence_available: bool) -> bool:
    if not fill_evidence_available:
        return False
    missing = PROVENANCE_FILL_COLUMNS.difference(fills.columns)
    if missing:
        return False
    execution_modes = fills["execution_mode"].astype(str).str.strip().str.lower()
    evidence_sources = fills["evidence_source"].astype(str).str.strip().str.lower()
    required_non_empty = ["venue", "capture_id", "order_id", "client_order_id", "exchange_timestamp"]
    non_empty = [_non_empty_string_column(fills, column).all() for column in required_non_empty]
    return bool(
        execution_modes.isin(ALLOWED_EXECUTION_MODES).all()
        and not evidence_sources.isin(BLOCKED_EVIDENCE_SOURCES).any()
        and all(non_empty)
    )


def _signal_provenance_clean(fills: pd.DataFrame, *, fill_evidence_available: bool) -> bool:
    if not fill_evidence_available:
        return False
    missing = SIGNAL_PROVENANCE_COLUMNS.difference(fills.columns)
    if missing:
        return False
    required_non_empty = ["signal_id", "signal_source", "market_source"]
    non_empty = [_non_empty_string_column(fills, column).all() for column in required_non_empty]
    signal_sources = fills["signal_source"].astype(str).str.strip().str.lower()
    market_sources = fills["market_source"].astype(str).str.strip().str.lower()
    return bool(
        all(non_empty)
        and not signal_sources.isin(BLOCKED_SIGNAL_SOURCES).any()
        and not market_sources.isin(BLOCKED_MARKET_SOURCES).any()
    )


def _latest_execution_timestamp(fills: pd.DataFrame) -> pd.Timestamp | None:
    timestamps: list[pd.Timestamp] = []
    for column in ("timestamp", "exchange_timestamp"):
        if column not in fills.columns:
            continue
        values = pd.to_datetime(fills[column], utc=True, errors="coerce", format="mixed").dropna()
        if values.empty:
            continue
        timestamps.append(pd.Timestamp(values.max()))
    if not timestamps:
        return None
    return max(timestamps)


def _recent_execution_evidence_clean(
    fills: pd.DataFrame,
    *,
    fill_evidence_available: bool,
    validation_time: pd.Timestamp,
) -> tuple[bool, str | None, float | None]:
    if not fill_evidence_available:
        return False, None, None
    latest = _latest_execution_timestamp(fills)
    if latest is None:
        return False, None, None
    generated_at = pd.Timestamp(validation_time)
    if generated_at.tzinfo is None:
        generated_at = generated_at.tz_localize("UTC")
    else:
        generated_at = generated_at.tz_convert("UTC")
    age_days = (generated_at - latest).total_seconds() / 86_400.0
    return (
        bool(0.0 <= age_days <= MAX_EXECUTION_EVIDENCE_AGE_DAYS),
        latest.isoformat(),
        round(float(age_days), 6),
    )


def _execution_validation_payload(
    *,
    fills: pd.DataFrame,
    kill_switch_events: pd.DataFrame,
    secret_findings: list[dict[str, Any]],
    validation_time: pd.Timestamp | None = None,
) -> dict[str, Any]:
    generated_at = validation_time or pd.Timestamp.now(tz=UTC)
    fill_count = int(len(fills))
    required_columns = BASE_FILL_COLUMNS.union(PROVENANCE_FILL_COLUMNS)
    missing_columns = sorted(required_columns.difference(fills.columns))
    missing_base_columns = sorted(BASE_FILL_COLUMNS.difference(fills.columns))
    missing_provenance_columns = sorted(PROVENANCE_FILL_COLUMNS.difference(fills.columns))
    missing_signal_provenance_columns = sorted(SIGNAL_PROVENANCE_COLUMNS.difference(fills.columns))
    fill_evidence_available = fill_count >= MIN_EXECUTION_FILLS and not missing_columns

    statuses = fills["status"].astype(str).str.strip().str.lower() if "status" in fills.columns else pd.Series(dtype=str)
    filled_status_clean = bool(fill_evidence_available and statuses.eq("filled").all())
    execution_provenance_clean = _execution_provenance_clean(fills, fill_evidence_available=fill_evidence_available)
    signal_provenance_clean = _signal_provenance_clean(fills, fill_evidence_available=fill_evidence_available)
    slippage = _slippage_bps(fills) if fill_evidence_available else pd.Series(dtype=float)
    max_slippage_bps_p95 = None if slippage.dropna().empty else round(float(slippage.quantile(0.95)), 6)
    slippage_clean = bool(max_slippage_bps_p95 is not None and max_slippage_bps_p95 <= MAX_SLIPPAGE_BPS_P95)
    recent_execution_evidence_clean, latest_execution_timestamp, execution_evidence_age_days = (
        _recent_execution_evidence_clean(
            fills,
            fill_evidence_available=fill_evidence_available,
            validation_time=pd.Timestamp(generated_at),
        )
    )
    kill_switch_tested = _kill_switch_tested(kill_switch_events)
    secrets_present = bool(secret_findings)

    checks = {
        "fill_evidence_available": fill_evidence_available,
        "filled_status_clean": filled_status_clean,
        "execution_provenance_clean": execution_provenance_clean,
        "signal_provenance_clean": signal_provenance_clean,
        "slippage_p95_clean": slippage_clean,
        "recent_execution_evidence_clean": recent_execution_evidence_clean,
        "kill_switch_tested": kill_switch_tested,
        "secrets_absent_from_repo": not secrets_present,
    }
    failed = [name for name, passed in checks.items() if not passed]
    passed = not failed
    status = "execution_validation_passed" if passed else "execution_validation_missing_evidence"
    if fill_evidence_available and failed:
        status = "execution_validation_failed"
    return {
        "version": "v205_btcusdc_execution_validation",
        "config": {
            "min_execution_fills": MIN_EXECUTION_FILLS,
            "max_slippage_bps_p95": MAX_SLIPPAGE_BPS_P95,
            "max_execution_evidence_age_days": MAX_EXECUTION_EVIDENCE_AGE_DAYS,
            "changes_strategy_thresholds": False,
            "places_live_orders": False,
        },
        "evidence": {
            "generated_at": pd.Timestamp(generated_at).isoformat(),
            "fill_count": fill_count,
            "missing_fill_columns": missing_columns,
            "missing_base_fill_columns": missing_base_columns,
            "missing_provenance_columns": missing_provenance_columns,
            "missing_signal_provenance_columns": missing_signal_provenance_columns,
            "latest_execution_timestamp": latest_execution_timestamp,
            "execution_evidence_age_days": execution_evidence_age_days,
            "kill_switch_event_count": int(len(kill_switch_events)),
            "secret_finding_count": int(len(secret_findings)),
        },
        "checks": checks,
        "decision": {
            "status": status,
            "execution_validation_passed": passed,
            "kill_switch_tested": kill_switch_tested,
            "secrets_present_in_repo": secrets_present,
            "max_slippage_bps_p95": max_slippage_bps_p95,
            "failed_checks": failed,
            "message": (
                "Execution validation evidence is clean."
                if passed
                else "Do not use real money. Execution evidence is missing or failed."
            ),
        },
        "secret_findings": secret_findings,
    }


def _tracked_files() -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    return [ROOT / line for line in result.stdout.splitlines() if line]


def _scan_repo_for_secret_findings() -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in _tracked_files():
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            match = SECRET_ASSIGNMENT.search(line)
            if match is None:
                continue
            value = match.group(5).strip().lower()
            if value in PLACEHOLDER_VALUES:
                continue
            findings.append({"path": str(path.relative_to(ROOT)), "line": lineno, "key": match.group(1)})
    return findings


def _write_report(payload: dict[str, Any], *, fills_path: Path, kill_switch_path: Path) -> None:
    decision = payload["decision"]
    evidence = payload["evidence"]
    checks = payload["checks"]
    lines = [
        "# Research V205 BTCUSDC Execution Validation",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Execution validation passed: `{decision['execution_validation_passed']}`",
        f"- Failed checks: `{', '.join(decision['failed_checks']) if decision['failed_checks'] else 'none'}`",
        f"- Message: {decision['message']}",
        "",
        "## Inputs",
        "",
        f"- Fill audit CSV: `{fills_path}`",
        f"- Kill-switch event CSV: `{kill_switch_path}`",
        "",
        "## Gate Checks",
        "",
        "| Check | Passed | Evidence |",
        "|---|---:|---|",
        f"| Fill evidence available | {checks['fill_evidence_available']} | fill_count={evidence['fill_count']}; missing_base_columns={evidence['missing_base_fill_columns']}; missing_provenance_columns={evidence['missing_provenance_columns']} |",
        f"| Filled status clean | {checks['filled_status_clean']} | requires every fill status to be `filled` |",
        f"| Execution provenance clean | {checks['execution_provenance_clean']} | requires venue, execution mode, evidence source, capture id, order id, client order id, and exchange timestamp |",
        f"| Signal provenance clean | {checks['signal_provenance_clean']} | missing_signal_provenance_columns={evidence['missing_signal_provenance_columns']}; blocks manual, synthetic, backtest, unknown, or blank signal/market sources |",
        f"| Slippage p95 clean | {checks['slippage_p95_clean']} | max_slippage_bps_p95={decision['max_slippage_bps_p95']} |",
        f"| Recent execution evidence clean | {checks['recent_execution_evidence_clean']} | latest_execution_timestamp={evidence['latest_execution_timestamp']}; execution_evidence_age_days={evidence['execution_evidence_age_days']}; max_age_days={payload['config']['max_execution_evidence_age_days']} |",
        f"| Kill switch tested | {checks['kill_switch_tested']} | kill_switch_event_count={evidence['kill_switch_event_count']} |",
        f"| Secrets absent from repo | {checks['secrets_absent_from_repo']} | secret_finding_count={evidence['secret_finding_count']} |",
        "",
        "## Iteration Metrics",
        "",
        "| Metric | V205 |",
        "|---|---:|",
        "| Strategy thresholds changed | No |",
        "| Entry/exit logic changed | No |",
        "| Leverage logic changed | No |",
        "| New backtest return improvement claimed | No |",
        "| Places live orders | No |",
        f"| Execution validation passed | {decision['execution_validation_passed']} |",
        f"| Fill evidence count | {evidence['fill_count']} |",
        f"| Execution provenance clean | {checks['execution_provenance_clean']} |",
        f"| Signal provenance clean | {checks['signal_provenance_clean']} |",
        f"| Recent execution evidence clean | {checks['recent_execution_evidence_clean']} |",
        f"| Kill switch tested | {decision['kill_switch_tested']} |",
        f"| Secrets present in repo | {decision['secrets_present_in_repo']} |",
        "",
        "## Interpretation",
        "",
        "V205 does not place live orders and does not change the trading strategy. It only validates whether external execution evidence is strong enough for V204 to consider the execution gate.",
        "",
        "This remains blocked for real-money use until clean fill evidence, order-level execution provenance, a tested kill switch, and a clean secret scan are all present.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run(*, fills_path: Path = DEFAULT_FILLS, kill_switch_path: Path = DEFAULT_KILL_SWITCH_EVENTS) -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = _execution_validation_payload(
        fills=_read_csv_or_empty(fills_path),
        kill_switch_events=_read_csv_or_empty(kill_switch_path),
        secret_findings=_scan_repo_for_secret_findings(),
    )
    (OUT_DIR / "execution_validation_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, fills_path=fills_path, kill_switch_path=kill_switch_path)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate BTCUSDC execution evidence for real-money readiness gates.")
    parser.add_argument("--fills", default=str(DEFAULT_FILLS))
    parser.add_argument("--kill-switch-events", default=str(DEFAULT_KILL_SWITCH_EVENTS))
    args = parser.parse_args()
    payload = run(fills_path=Path(args.fills), kill_switch_path=Path(args.kill_switch_events))
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
