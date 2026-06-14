from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.request import urlopen

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import (
    aggregate_btcusdc_aggtrades_to_bars,
    build_delayed_candidate_trade_ledger,
    load_btcusdc_aggtrades,
    summarize_last_two_year_stability,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_btcusdc_v90_forward_monitoring as v90  # noqa: E402


SYMBOL = "ETHUSDC"
END_TS = pd.Timestamp("2026-06-12T23:59:00Z")
OUT_DIR = ROOT / "runs" / "research_v91_ethusdc_v90_transfer_test"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V91_ETHUSDC_V90_TRANSFER_TEST_RESULTS.md"
BASE_URL = "https://data.binance.vision/data/futures/um"
ENTRY_DELAYS = v90.ENTRY_DELAYS
EXTRA_COST_BPS = v90.EXTRA_COST_BPS


def _binance_aggtrade_url(symbol: str, frequency: str, date_value: str) -> str:
    sym = str(symbol).upper()
    freq = str(frequency).lower()
    if freq not in {"daily", "monthly"}:
        raise ValueError("frequency must be daily or monthly")
    return f"{BASE_URL}/{freq}/aggTrades/{sym}/{sym}-aggTrades-{date_value}.zip"


def _binance_aggtrade_path(symbol: str, frequency: str, date_value: str) -> Path:
    sym = str(symbol).upper()
    freq = str(frequency).lower()
    return ROOT / "data" / "binance_public" / "um" / freq / "aggTrades" / sym / f"{sym}-aggTrades-{date_value}.zip"


def _source_specs() -> list[dict[str, str]]:
    monthly = pd.period_range("2024-06", "2026-05", freq="M")
    daily = pd.date_range("2026-06-01", "2026-06-12", freq="D", tz="UTC")
    rows: list[dict[str, str]] = []
    for period in monthly:
        rows.append({"frequency": "monthly", "date_value": str(period)})
    for day in daily:
        rows.append({"frequency": "daily", "date_value": day.date().isoformat()})
    return rows


def _download_file(url: str, target: Path) -> dict[str, object]:
    if target.exists() and target.stat().st_size > 0:
        return {"url": url, "path": str(target), "bytes": int(target.stat().st_size), "downloaded": False}
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with urlopen(url, timeout=120) as response:  # noqa: S310 - user-requested Binance public data download
        with tmp.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
    tmp.replace(target)
    return {"url": url, "path": str(target), "bytes": int(target.stat().st_size), "downloaded": True}


def _ensure_source_files(symbol: str = SYMBOL) -> list[Path]:
    manifest_rows: list[dict[str, object]] = []
    paths: list[Path] = []
    for spec in _source_specs():
        url = _binance_aggtrade_url(symbol, spec["frequency"], spec["date_value"])
        path = _binance_aggtrade_path(symbol, spec["frequency"], spec["date_value"])
        result = _download_file(url, path)
        manifest_rows.append({**spec, **result})
        paths.append(path)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(manifest_rows).to_csv(OUT_DIR / "v91_ethusdc_download_manifest.csv", index=False)
    return paths


def _cached_bars_path(path: Path) -> Path:
    return OUT_DIR / "bar_cache" / f"{path.stem}_1m_flow_bars.csv"


def _bars_from_source_file(path: Path) -> pd.DataFrame:
    cache = _cached_bars_path(path)
    if cache.exists():
        bars = pd.read_csv(cache)
        bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
        return bars
    trades = load_btcusdc_aggtrades([path])
    bars = aggregate_btcusdc_aggtrades_to_bars(trades)
    cache.parent.mkdir(parents=True, exist_ok=True)
    bars.to_csv(cache, index=False)
    return bars


def _build_ethusdc_bars(paths: list[Path]) -> pd.DataFrame:
    frames = [_bars_from_source_file(path) for path in paths]
    if not frames:
        raise ValueError("no ETHUSDC source files")
    bars = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset=["timestamp"], keep="last")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars["replay_date"] = bars["timestamp"].dt.date.astype(str)
    return bars


def _extra_cost_summary(trades: pd.DataFrame) -> pd.DataFrame:
    pnl = pd.to_numeric(trades.get("net_pnl_bps", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    rows = []
    for extra in EXTRA_COST_BPS:
        adjusted = pnl - float(extra)
        rows.append(
            {
                "extra_cost_bps": float(extra),
                "trades": int(len(adjusted)),
                "total_net_pnl_bps": float(adjusted.sum()),
                "mean_net_pnl_bps": float(adjusted.mean()) if len(adjusted) else 0.0,
                "win_rate": float((adjusted > 0.0).mean()) if len(adjusted) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _delay_summary(delay_ledgers: pd.DataFrame) -> pd.DataFrame:
    if delay_ledgers.empty:
        return pd.DataFrame(columns=["entry_delay_minutes", "trades", "total_net_pnl_bps", "mean_net_pnl_bps", "win_rate"])
    rows = []
    for delay, group in delay_ledgers.groupby("entry_delay_minutes", sort=True):
        pnl = pd.to_numeric(group["net_pnl_bps"], errors="coerce").fillna(0.0)
        rows.append(
            {
                "entry_delay_minutes": int(delay),
                "trades": int(len(group)),
                "total_net_pnl_bps": float(pnl.sum()),
                "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                "win_rate": float((pnl > 0.0).mean()) if len(pnl) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _write_report(payload: dict[str, object], policy_table: pd.DataFrame) -> None:
    lines = [
        "# Research V91 ETHUSDC V90 Transfer Test Results",
        "",
        "## Decision",
        "",
        f"- Symbol: `{payload['symbol']}`",
        f"- Data start: `{payload['data']['combined_start']}`",
        f"- Data end: `{payload['data']['combined_end']}`",
        f"- Two-year start: `{payload['period']['start_timestamp']}`",
        f"- Two-year end: `{payload['period']['end_timestamp']}`",
        f"- Stable policies: `{payload['decision']['stable_policy_count']}` / `{payload['decision']['policy_count']}`",
        f"- Best stable policy: `{payload['decision']['best_stable_policy']}`",
        "",
        "## Policy Table",
        "",
        policy_table.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "This is a direct ETHUSDC transfer test of the fixed BTCUSDC V90 policy family. It does not retune thresholds or hour filters for ETHUSDC.",
        "",
        "Passing this test would indicate transferability evidence; failing it means the BTCUSDC edge should not be assumed to work on ETHUSDC without separate design work.",
        "",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = _ensure_source_files(SYMBOL)
    bars = _build_ethusdc_bars(paths)
    bars.to_csv(OUT_DIR / "v91_ethusdc_aggtrade_1m_flow_bars.csv", index=False)
    candidate = v90._candidate()
    v69 = json.loads(v90.V69_SUMMARY.read_text(encoding="utf-8"))
    excluded_hours = [int(hour) for hour in v69["hour_gate"]["excluded_hours"]]
    end_ts = min(END_TS, bars["timestamp"].max())
    start_ts = end_ts - pd.DateOffset(years=2)
    policies = [
        {
            "policy": "v69_v87_oversold_short_veto_-650",
            "description": "BTCUSDC V69 hour gate plus V87 oversold-short veto at -650 bps, transferred to ETHUSDC.",
        },
        {
            "policy": "v89_conservative_same_family_-550",
            "description": "BTCUSDC V89 conservative same-family oversold-short veto at -550 bps, transferred to ETHUSDC.",
        },
        {
            "policy": "v89_mechanical_remove_hours_0_2_3_4",
            "description": "BTCUSDC V89 mechanical hour removal on top of the V87 short veto, transferred to ETHUSDC.",
        },
    ]

    ledgers: dict[int, pd.DataFrame] = {}
    for delay in ENTRY_DELAYS:
        ledgers[int(delay)] = v90._normalize_ledger(build_delayed_candidate_trade_ledger(bars, candidate, entry_delay_minutes=int(delay)))

    policy_payloads: list[dict[str, object]] = []
    policy_rows: list[dict[str, object]] = []
    for spec in policies:
        policy = str(spec["policy"])
        primary = ledgers[0]
        kept_primary = primary.loc[v90._policy_mask(policy, primary, excluded_hours)].copy().reset_index(drop=True)
        scoped_primary = kept_primary.loc[(kept_primary["timestamp"] >= start_ts) & (kept_primary["timestamp"] <= end_ts)].copy().reset_index(drop=True)

        all_scoped_delay = []
        for _, ledger in ledgers.items():
            kept = ledger.loc[v90._policy_mask(policy, ledger, excluded_hours)].copy().reset_index(drop=True)
            scoped = kept.loc[(kept["timestamp"] >= start_ts) & (kept["timestamp"] <= end_ts)].copy().reset_index(drop=True)
            all_scoped_delay.append(scoped)
        scoped_delay = pd.concat(all_scoped_delay, ignore_index=True) if all_scoped_delay else pd.DataFrame()

        delay_summary = _delay_summary(scoped_delay)
        extra = _extra_cost_summary(scoped_primary)
        stability = summarize_last_two_year_stability(
            kept_primary,
            delay_summary=delay_summary,
            extra_cost_summary=extra,
            start_timestamp=start_ts,
            end_timestamp=end_ts,
        )
        months = pd.DataFrame(stability["months"]["rows"])
        rolling = pd.DataFrame(stability["rolling"]["rows"])
        scoped_primary.to_csv(OUT_DIR / f"v91_{policy}_two_year_trade_ledger.csv", index=False)
        scoped_delay.to_csv(OUT_DIR / f"v91_{policy}_two_year_delay_ledgers.csv", index=False)
        delay_summary.to_csv(OUT_DIR / f"v91_{policy}_two_year_delay_summary.csv", index=False)
        extra.to_csv(OUT_DIR / f"v91_{policy}_two_year_extra_cost_summary.csv", index=False)
        months.to_csv(OUT_DIR / f"v91_{policy}_two_year_months.csv", index=False)
        rolling.to_csv(OUT_DIR / f"v91_{policy}_two_year_rolling_windows.csv", index=False)

        aggregate = stability["aggregate"]
        month_summary = stability["months"]
        rolling_summary = stability["rolling"]
        decision = stability["decision"]
        policy_payloads.append(
            {
                **spec,
                "stability": stability,
                "outputs": {
                    "two_year_trade_ledger": str(OUT_DIR / f"v91_{policy}_two_year_trade_ledger.csv"),
                    "two_year_delay_ledgers": str(OUT_DIR / f"v91_{policy}_two_year_delay_ledgers.csv"),
                    "two_year_delay_summary": str(OUT_DIR / f"v91_{policy}_two_year_delay_summary.csv"),
                    "two_year_extra_cost_summary": str(OUT_DIR / f"v91_{policy}_two_year_extra_cost_summary.csv"),
                    "two_year_months": str(OUT_DIR / f"v91_{policy}_two_year_months.csv"),
                    "two_year_rolling_windows": str(OUT_DIR / f"v91_{policy}_two_year_rolling_windows.csv"),
                },
            }
        )
        policy_rows.append(
            {
                "policy": policy,
                "stable_enough": bool(decision["stable_enough"]),
                "failed_checks": ";".join(decision["failed_checks"]),
                "trade_count": int(aggregate["trade_count"]),
                "total_net_pnl_bps": float(aggregate["total_net_pnl_bps"]),
                "mean_net_pnl_bps": float(aggregate["mean_net_pnl_bps"]),
                "win_rate": float(aggregate["win_rate"]),
                "max_drawdown_bps": float(aggregate["max_drawdown_bps"]),
                "required_extra_cost_total_net_pnl_bps": float(aggregate["required_extra_cost_total_net_pnl_bps"]),
                "worst_delay_total_net_pnl_bps": float(aggregate["worst_delay_total_net_pnl_bps"]),
                "active_positive_month_rate": float(month_summary["active_positive_month_rate"]),
                "calendar_positive_month_rate": float(month_summary["calendar_positive_month_rate"]),
                "rolling_3m_positive_rate": float(rolling_summary["rolling_3m"]["positive_rate"]),
                "rolling_6m_positive_rate": float(rolling_summary["rolling_6m"]["positive_rate"]),
                "rolling_12m_positive_rate": float(rolling_summary["rolling_12m"]["positive_rate"]),
                "rolling_3m_worst_net_pnl_bps": float(rolling_summary["rolling_3m"]["worst_total_net_pnl_bps"]),
                "rolling_6m_worst_net_pnl_bps": float(rolling_summary["rolling_6m"]["worst_total_net_pnl_bps"]),
            }
        )

    policy_table = pd.DataFrame(policy_rows).sort_values(
        ["stable_enough", "total_net_pnl_bps", "trade_count"],
        ascending=[False, False, False],
    )
    stable = policy_table.loc[policy_table["stable_enough"].astype(bool)].copy()
    best_stable_policy = str(stable.iloc[0]["policy"]) if len(stable) else None
    policy_table.to_csv(OUT_DIR / "v91_ethusdc_policy_table.csv", index=False)
    payload = {
        "version": "v91_ethusdc_v90_transfer_test",
        "symbol": SYMBOL,
        "candidate": candidate.to_dict(),
        "period": {
            "start_timestamp": start_ts.isoformat(),
            "end_timestamp": end_ts.isoformat(),
        },
        "data": {
            "source_file_count": int(len(paths)),
            "combined_bar_count": int(len(bars)),
            "combined_start": bars["timestamp"].min().isoformat(),
            "combined_end": bars["timestamp"].max().isoformat(),
        },
        "decision": {
            "policy_count": int(len(policy_table)),
            "stable_policy_count": int(policy_table["stable_enough"].astype(bool).sum()),
            "best_stable_policy": best_stable_policy,
        },
        "policies": policy_payloads,
        "outputs": {
            "summary_json": str(OUT_DIR / "v91_ethusdc_summary.json"),
            "policy_table": str(OUT_DIR / "v91_ethusdc_policy_table.csv"),
            "aggtrade_1m_flow_bars": str(OUT_DIR / "v91_ethusdc_aggtrade_1m_flow_bars.csv"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v91_ethusdc_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, policy_table)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
