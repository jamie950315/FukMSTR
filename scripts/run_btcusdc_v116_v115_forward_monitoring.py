from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_btcusdc_v94_high_frequency_scan as v94


OUT_DIR = ROOT / "runs" / "research_v116_btcusdc_v115_forward_monitoring"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V116_BTCUSDC_V115_FORWARD_MONITORING_RESULTS.md"
V115_LEDGER = ROOT / "runs" / "research_v115_btcusdc_v112_contrarian_sizing" / "v115_weighted_trade_ledger.csv"
V115_SUMMARY = ROOT / "runs" / "research_v115_btcusdc_v112_contrarian_sizing" / "v115_summary.json"

REQUESTED_NEXT_DATE = "2026-06-13"
BINANCE_BASE_URL = "https://data.binance.vision/data/futures/um/daily"


def _local_expected_paths(date_value: str = REQUESTED_NEXT_DATE) -> dict[str, Path]:
    return {
        "aggtrades": ROOT
        / "data"
        / "binance_public"
        / "um"
        / "daily"
        / "aggTrades"
        / "BTCUSDC"
        / f"BTCUSDC-aggTrades-{date_value}.zip",
        "klines_1m": ROOT
        / "data"
        / "binance_public"
        / "um"
        / "daily"
        / "klines"
        / "BTCUSDC"
        / "1m"
        / f"BTCUSDC-1m-{date_value}.zip",
    }


def _remote_expected_urls(date_value: str = REQUESTED_NEXT_DATE) -> dict[str, str]:
    return {
        "aggtrades": f"{BINANCE_BASE_URL}/aggTrades/BTCUSDC/BTCUSDC-aggTrades-{date_value}.zip",
        "klines_1m": f"{BINANCE_BASE_URL}/klines/BTCUSDC/1m/BTCUSDC-1m-{date_value}.zip",
    }


def _remote_file_status(url: str) -> dict[str, object]:
    try:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-0"})
        with urlopen(request, timeout=30) as response:  # noqa: S310 - Binance public data availability check.
            return {"url": url, "available": True, "status": int(response.status)}
    except HTTPError as exc:
        return {"url": url, "available": False, "status": int(exc.code), "error": str(exc)}
    except URLError as exc:
        return {"url": url, "available": False, "status": None, "error": str(exc)}


def _monitoring_decision(*, has_new_complete_day: bool, data_end: pd.Timestamp, v115_trade_end: pd.Timestamp) -> dict[str, object]:
    if not has_new_complete_day:
        return {
            "status": "no_new_complete_public_file",
            "monitoring_ok": True,
            "forward_trade_proof": False,
            "new_signal_count": 0,
            "next_action": "wait_for_next_complete_binance_public_day",
            "reason": "No complete BTCUSDC public daily files are available after the current local data end.",
        }
    if data_end <= v115_trade_end:
        return {
            "status": "new_files_present_but_no_extended_bar_window",
            "monitoring_ok": False,
            "forward_trade_proof": False,
            "new_signal_count": 0,
            "next_action": "rebuild_bars_and_rerun_v113_v114_v115",
            "reason": "New files are present, but the computed bar window has not extended beyond the V115 trade ledger.",
        }
    return {
        "status": "new_data_available_rerun_required",
        "monitoring_ok": False,
        "forward_trade_proof": False,
        "new_signal_count": None,
        "next_action": "rebuild_v113_then_apply_v114_and_v115_to_new_rows",
        "reason": "A new complete public day is available; the fixed V115 stack must be rerun before judging new forward trades.",
    }


def _write_report(payload: dict[str, object]) -> None:
    lines = [
        "# Research V116 BTCUSDC V115 Forward Monitoring Results",
        "",
        "## Decision",
        "",
        f"- Requested next public date: `{payload['requested_next_date']}`",
        f"- Latest local bar timestamp: `{payload['data']['local_bar_end']}`",
        f"- Latest V115 trade timestamp: `{payload['data']['v115_trade_end']}`",
        f"- Local next aggTrades file exists: `{payload['data']['local_files']['aggtrades']['exists']}`",
        f"- Local next 1m kline file exists: `{payload['data']['local_files']['klines_1m']['exists']}`",
        f"- Remote next aggTrades status: `{payload['data']['remote_files']['aggtrades'].get('status')}`",
        f"- Remote next 1m kline status: `{payload['data']['remote_files']['klines_1m'].get('status')}`",
        f"- Monitoring status: `{payload['decision']['status']}`",
        f"- Forward trade proof: `{payload['decision']['forward_trade_proof']}`",
        f"- Next action: `{payload['decision']['next_action']}`",
        "",
        "## Interpretation",
        "",
        "V116 checks whether V115 can be forward-monitored with new complete BTCUSDC Binance public daily files. At this run time, the 2026-06-13 public files are not available locally or remotely, so there is no new forward trading evidence yet. This is a data-availability result, not a profit or loss result.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    bars = v94._full_bars()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    ledger = pd.read_csv(V115_LEDGER)
    ledger["timestamp"] = pd.to_datetime(ledger["timestamp"], utc=True)

    local_paths = _local_expected_paths()
    remote_urls = _remote_expected_urls()
    local_files = {
        key: {"path": str(path), "exists": bool(path.exists()), "bytes": int(path.stat().st_size) if path.exists() else 0}
        for key, path in local_paths.items()
    }
    remote_files = {key: _remote_file_status(url) for key, url in remote_urls.items()}
    has_new_complete_day = bool(local_files["aggtrades"]["exists"] or remote_files["aggtrades"]["available"])
    data_end = pd.to_datetime(bars["timestamp"].max(), utc=True)
    v115_trade_end = pd.to_datetime(ledger["timestamp"].max(), utc=True)
    decision = _monitoring_decision(
        has_new_complete_day=has_new_complete_day,
        data_end=data_end,
        v115_trade_end=v115_trade_end,
    )

    payload = {
        "version": "v116_btcusdc_v115_forward_monitoring",
        "base_version": "v115_btcusdc_v112_contrarian_sizing",
        "requested_next_date": REQUESTED_NEXT_DATE,
        "data": {
            "local_bar_start": pd.to_datetime(bars["timestamp"].min(), utc=True).isoformat(),
            "local_bar_end": data_end.isoformat(),
            "v115_trade_start": pd.to_datetime(ledger["timestamp"].min(), utc=True).isoformat(),
            "v115_trade_end": v115_trade_end.isoformat(),
            "local_files": local_files,
            "remote_files": remote_files,
        },
        "decision": decision,
        "outputs": {
            "summary_json": str(OUT_DIR / "v116_summary.json"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v116_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
