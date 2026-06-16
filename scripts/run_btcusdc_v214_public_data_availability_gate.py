from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v214_public_data_availability_gate"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V214_BTCUSDC_PUBLIC_DATA_AVAILABILITY_GATE.md"
AGGTRADE_DIR = ROOT / "data" / "binance_public" / "um" / "daily" / "aggTrades" / "BTCUSDC"
KLINE_DIR = ROOT / "data" / "binance_public" / "um" / "daily" / "klines" / "BTCUSDC" / "1m"
BASE_URL = "https://data.binance.vision/data/futures/um/daily"


def _date_from_name(path: Path, *, prefix: str, suffix: str) -> str | None:
    name = path.name
    if not (name.startswith(prefix) and name.endswith(suffix)):
        return None
    value = name.removeprefix(prefix).removesuffix(suffix)
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _local_aggtrade_dates(path: Path = AGGTRADE_DIR) -> set[str]:
    return {
        day
        for day in (_date_from_name(item, prefix="BTCUSDC-aggTrades-", suffix=".zip") for item in path.glob("*.zip"))
        if day is not None
    }


def _local_kline_dates(path: Path = KLINE_DIR) -> set[str]:
    return {
        day
        for day in (_date_from_name(item, prefix="BTCUSDC-1m-", suffix=".zip") for item in path.glob("*.zip"))
        if day is not None
    }


def _latest_completed_utc_date(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    return (current.astimezone(timezone.utc).date() - timedelta(days=1)).isoformat()


def _http_status(url: str, *, timeout_sec: float = 10.0) -> int:
    request = Request(url, method="HEAD")
    try:
        with urlopen(request, timeout=timeout_sec) as response:
            return int(response.status)
    except HTTPError as exc:
        return int(exc.code)
    except URLError:
        return 0


def _remote_status_for_date(day: str) -> dict[str, int]:
    return {
        "aggtrade_http_status": _http_status(f"{BASE_URL}/aggTrades/BTCUSDC/BTCUSDC-aggTrades-{day}.zip"),
        "kline_http_status": _http_status(f"{BASE_URL}/klines/BTCUSDC/1m/BTCUSDC-1m-{day}.zip"),
    }


def _payload_for_public_data_availability(
    *,
    latest_completed_utc_date: str,
    remote_status: dict[str, dict[str, int]],
    local_aggtrade_dates: set[str],
    local_kline_dates: set[str],
) -> dict[str, Any]:
    latest_status = remote_status.get(latest_completed_utc_date, {})
    latest_aggtrade_published = latest_status.get("aggtrade_http_status") == 200
    latest_kline_published = latest_status.get("kline_http_status") == 200
    latest_published = latest_aggtrade_published and latest_kline_published

    published_dates = [
        day
        for day, status in sorted(remote_status.items())
        if status.get("aggtrade_http_status") == 200 and status.get("kline_http_status") == 200
    ]
    missing_local_aggtrade_dates = [day for day in published_dates if day not in local_aggtrade_dates]
    missing_local_kline_dates = [day for day in published_dates if day not in local_kline_dates]
    published_files_downloaded = not missing_local_aggtrade_dates and not missing_local_kline_dates
    remote_probe_available = latest_status.get("aggtrade_http_status", 0) > 0 and latest_status.get("kline_http_status", 0) > 0
    public_data_available = bool(remote_probe_available and latest_published and published_files_downloaded)

    checks = {
        "remote_probe_available": remote_probe_available,
        "latest_completed_utc_day_published": latest_published,
        "published_files_downloaded": published_files_downloaded,
    }
    failed = [name for name, passed in checks.items() if not passed]

    if not remote_probe_available:
        status = "public_data_probe_unavailable"
    elif not latest_published:
        status = "public_data_pending_publication"
    elif not published_files_downloaded:
        status = "public_data_missing_local_files"
    else:
        status = "public_data_availability_passed"

    return {
        "version": "v214_btcusdc_public_data_availability_gate",
        "config": {
            "symbol": "BTCUSDC",
            "market": "binance_um_futures",
            "latest_completed_utc_date": latest_completed_utc_date,
            "changes_strategy_thresholds": False,
            "changes_trade_side": False,
            "changes_leverage_logic": False,
            "places_live_orders": False,
            "promotes_real_money": False,
        },
        "evidence": {
            "remote_status": remote_status,
            "local_aggtrade_latest_date": max(local_aggtrade_dates) if local_aggtrade_dates else None,
            "local_kline_latest_date": max(local_kline_dates) if local_kline_dates else None,
            "missing_local_aggtrade_dates": missing_local_aggtrade_dates,
            "missing_local_kline_dates": missing_local_kline_dates,
        },
        "checks": checks,
        "decision": {
            "status": status,
            "public_data_available": public_data_available,
            "promote_to_real_money": False,
            "failed_checks": failed,
            "message": (
                "Latest completed UTC day is published and local public data files are present."
                if public_data_available
                else "Do not treat forward data as current. Public data publication or local downloads are incomplete."
            ),
        },
    }


def _write_report(payload: dict[str, Any]) -> None:
    decision = payload["decision"]
    evidence = payload["evidence"]
    checks = payload["checks"]
    latest = payload["config"]["latest_completed_utc_date"]
    remote = evidence["remote_status"].get(latest, {})
    lines = [
        "# Research V214 BTCUSDC Public Data Availability Gate",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Public data available: `{decision['public_data_available']}`",
        f"- Promote to real money: `{decision['promote_to_real_money']}`",
        f"- Failed checks: `{', '.join(decision['failed_checks']) if decision['failed_checks'] else 'none'}`",
        f"- Message: {decision['message']}",
        "",
        "## Gate Checks",
        "",
        "| Check | Passed | Evidence |",
        "|---|---:|---|",
        f"| Remote probe available | {checks['remote_probe_available']} | latest_completed_utc_date={latest} |",
        f"| Latest completed UTC day published | {checks['latest_completed_utc_day_published']} | aggtrade_http_status={remote.get('aggtrade_http_status')}; kline_http_status={remote.get('kline_http_status')} |",
        f"| Published files downloaded | {checks['published_files_downloaded']} | missing_aggtrade={evidence['missing_local_aggtrade_dates']}; missing_kline={evidence['missing_local_kline_dates']} |",
        "",
        "## Iteration Metrics",
        "",
        "| Metric | V214 |",
        "|---|---:|",
        "| Strategy thresholds changed | No |",
        "| Entry/exit logic changed | No |",
        "| Leverage logic changed | No |",
        "| New backtest return improvement claimed | No |",
        "| Places live orders | No |",
        f"| Public data available | {decision['public_data_available']} |",
        f"| Promote to real money | {decision['promote_to_real_money']} |",
        "",
        "## Interpretation",
        "",
        "V214 checks whether Binance public daily BTCUSDC files for the latest completed UTC day are published and present locally. It is a data-availability gate, not a strategy change.",
        "",
        "This does not create trades, tune thresholds, or claim new profitability. Real-money use remains blocked until the full readiness gate passes with current forward and execution evidence.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    latest_day = _latest_completed_utc_date()
    payload = _payload_for_public_data_availability(
        latest_completed_utc_date=latest_day,
        remote_status={latest_day: _remote_status_for_date(latest_day)},
        local_aggtrade_dates=_local_aggtrade_dates(),
        local_kline_dates=_local_kline_dates(),
    )
    (OUT_DIR / "v214_public_data_availability_gate_summary.json").write_text(
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
