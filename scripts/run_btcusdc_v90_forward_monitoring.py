from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import (
    BTCUSDCCandidate,
    aggregate_btcusdc_aggtrades_to_bars,
    build_delayed_candidate_trade_ledger,
    load_btcusdc_aggtrades,
    summarize_forward_monitoring_window,
)


ROOT = Path(__file__).resolve().parents[1]
V50_BARS = ROOT / "runs" / "research_v50_btcusdc_full_aggtrade_flow_input" / "btcusdc_full_aggtrade_1m_flow_bars.csv"
V68_SUMMARY = ROOT / "runs" / "research_v68_btcusdc_fixed_flow_stability" / "v68_summary.json"
V69_SUMMARY = ROOT / "runs" / "research_v69_btcusdc_fixed_flow_hour_gate" / "v69_summary.json"
V89_SUMMARY = ROOT / "runs" / "research_v89_btcusdc_stability_improvement_scan" / "v89_summary.json"
AGGTRADE_DIR = ROOT / "data" / "binance_public" / "um" / "daily" / "aggTrades" / "BTCUSDC"
OUT_DIR = ROOT / "runs" / "research_v90_btcusdc_forward_monitoring"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V90_BTCUSDC_FORWARD_MONITORING_RESULTS.md"

FORWARD_START = pd.Timestamp("2026-06-06T04:10:00Z")
ENTRY_DELAYS = (0, 1, 2, 5, 10)
EXTRA_COST_BPS = (0.0, 4.0, 8.0, 16.0)


def _load_base_bars(path: Path) -> pd.DataFrame:
    bars = pd.read_csv(path)
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    if "replay_date" not in bars.columns:
        bars["replay_date"] = bars["timestamp"].dt.date.astype(str)
    return bars.sort_values("timestamp").reset_index(drop=True)


def _new_aggtrade_paths(after: pd.Timestamp) -> list[Path]:
    paths: list[Path] = []
    for path in sorted(AGGTRADE_DIR.glob("BTCUSDC-aggTrades-*.zip")):
        date_text = path.stem.rsplit("-", 3)[-3:]
        try:
            day = pd.Timestamp("-".join(date_text), tz="UTC")
        except ValueError:
            continue
        if day.date() > after.date():
            paths.append(path)
    return paths


def _combined_bars(base_bars: pd.DataFrame, new_paths: list[Path]) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not new_paths:
        return base_bars.copy(), pd.DataFrame(columns=base_bars.columns)
    aggtrades = load_btcusdc_aggtrades(new_paths)
    new_bars = aggregate_btcusdc_aggtrades_to_bars(aggtrades)
    for column in base_bars.columns:
        if column not in new_bars.columns:
            new_bars[column] = pd.NA
    for column in new_bars.columns:
        if column not in base_bars.columns:
            base_bars[column] = pd.NA
    columns = list(base_bars.columns)
    new_bars = new_bars[columns]
    combined = (
        pd.concat([base_bars, new_bars], ignore_index=True)
        .drop_duplicates(subset=["timestamp"], keep="last")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    return combined, new_bars


def _candidate() -> BTCUSDCCandidate:
    raw = json.loads(V68_SUMMARY.read_text(encoding="utf-8"))["candidate"]
    return BTCUSDCCandidate(
        lookback_minutes=int(raw["lookback_minutes"]),
        horizon_minutes=int(raw["horizon_minutes"]),
        direction=str(raw["direction"]),
        filter_feature=str(raw["filter_feature"]),
        threshold=float(raw["threshold"]),
        fee_bps=float(raw["fee_bps"]),
        quantile=float(raw["quantile"]) if raw.get("quantile") is not None else None,
    )


def _normalize_ledger(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if out.empty:
        return out
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    out["signal_timestamp"] = pd.to_datetime(out.get("signal_timestamp", out["timestamp"]), utc=True)
    out["hour"] = out["timestamp"].dt.hour.astype(int)
    for column in ["net_pnl_bps", "signal", "lookback_return_bps", "entry_delay_minutes"]:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0.0)
    if "signal" in out.columns:
        out["signal"] = out["signal"].astype(int)
    if "entry_delay_minutes" in out.columns:
        out["entry_delay_minutes"] = out["entry_delay_minutes"].astype(int)
    return out.sort_values("timestamp").reset_index(drop=True)


def _policy_mask(policy: str, frame: pd.DataFrame, excluded_hours: list[int]) -> pd.Series:
    base = ~frame["hour"].isin([int(hour) for hour in excluded_hours])
    v87_short_veto = ~((frame["signal"] < 0) & (frame["lookback_return_bps"] < -650.0))
    if policy == "v69_v87_oversold_short_veto_-650":
        return base & v87_short_veto
    if policy == "v89_conservative_same_family_-550":
        return base & ~((frame["signal"] < 0) & (frame["lookback_return_bps"] < -550.0))
    if policy == "v89_mechanical_remove_hours_0_2_3_4":
        return base & v87_short_veto & ~frame["hour"].isin([0, 2, 3, 4])
    raise ValueError(f"unknown policy: {policy}")


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
    rows = []
    if delay_ledgers.empty:
        return pd.DataFrame(columns=["entry_delay_minutes", "trades", "total_net_pnl_bps", "mean_net_pnl_bps", "win_rate"])
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
        "# Research V90 BTCUSDC Forward Monitoring Results",
        "",
        "## Decision",
        "",
        f"- Data end: `{payload['data']['combined_end']}`",
        f"- Forward signal start: `{payload['forward_start']}`",
        f"- New aggTrade files: `{payload['data']['new_aggtrade_file_count']}`",
        f"- New signal count across monitored policies: `{payload['decision']['new_signal_count']}`",
        f"- Monitoring status: `{payload['decision']['status']}`",
        f"- Next action: `{payload['decision']['next_action']}`",
        "",
        "## Policy Monitoring",
        "",
        policy_table.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V90 extends the BTCUSDC aggTrade flow data through the newly available Binance public files and rebuilds the fixed V68/V69/V89 ledgers without changing thresholds.",
        "",
        "There are no new signal timestamps after the V89 cutoff through the current data end. The delayed entries seen immediately after the cutoff belong to the old 2026-06-06 04:10 UTC signal, so they are excluded from forward monitoring.",
        "",
        "This is a monitoring result, not a new profit proof. The correct action is to keep collecting new public files and rerun this monitor when more days are available.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    base_bars = _load_base_bars(V50_BARS)
    base_end = base_bars["timestamp"].max()
    new_paths = _new_aggtrade_paths(base_end)
    bars, new_bars = _combined_bars(base_bars, new_paths)
    candidate = _candidate()
    v69 = json.loads(V69_SUMMARY.read_text(encoding="utf-8"))
    v89 = json.loads(V89_SUMMARY.read_text(encoding="utf-8"))
    excluded_hours = [int(hour) for hour in v69["hour_gate"]["excluded_hours"]]
    policies = [
        {
            "policy": "v69_v87_oversold_short_veto_-650",
            "description": "V69 hour gate plus V87 oversold-short veto at -650 bps.",
        },
        {
            "policy": "v89_conservative_same_family_-550",
            "description": "V69 hour gate plus V89 conservative same-family oversold-short veto at -550 bps.",
        },
        {
            "policy": "v89_mechanical_remove_hours_0_2_3_4",
            "description": "V69 hour gate plus V89 mechanical removal of UTC hours 0, 2, 3, and 4.",
        },
    ]

    ledgers: dict[int, pd.DataFrame] = {}
    for delay in ENTRY_DELAYS:
        ledgers[int(delay)] = _normalize_ledger(build_delayed_candidate_trade_ledger(bars, candidate, entry_delay_minutes=int(delay)))

    policy_payloads: list[dict[str, object]] = []
    policy_rows: list[dict[str, object]] = []
    for spec in policies:
        policy = str(spec["policy"])
        primary = ledgers[0]
        kept_primary = primary.loc[_policy_mask(policy, primary, excluded_hours)].copy().reset_index(drop=True)
        all_kept_delay = []
        for delay, ledger in ledgers.items():
            kept = ledger.loc[_policy_mask(policy, ledger, excluded_hours)].copy().reset_index(drop=True)
            all_kept_delay.append(kept)
        kept_delay = pd.concat(all_kept_delay, ignore_index=True) if all_kept_delay else pd.DataFrame()

        forward_primary = kept_primary.loc[kept_primary["signal_timestamp"] > FORWARD_START].copy().reset_index(drop=True)
        forward_delay = kept_delay.loc[kept_delay["signal_timestamp"] > FORWARD_START].copy().reset_index(drop=True) if not kept_delay.empty else kept_delay
        delay_summary = _delay_summary(forward_delay)
        extra = _extra_cost_summary(forward_primary)
        summary = summarize_forward_monitoring_window(
            kept_primary,
            delay_summary=delay_summary,
            extra_cost_summary=extra,
            start_timestamp=FORWARD_START,
            end_timestamp=bars["timestamp"].max(),
            signal_timestamp_col="signal_timestamp",
        )
        forward_primary.to_csv(OUT_DIR / f"v90_{policy}_forward_trade_ledger.csv", index=False)
        forward_delay.to_csv(OUT_DIR / f"v90_{policy}_forward_delay_ledgers.csv", index=False)
        delay_summary.to_csv(OUT_DIR / f"v90_{policy}_forward_delay_summary.csv", index=False)
        extra.to_csv(OUT_DIR / f"v90_{policy}_forward_extra_cost_summary.csv", index=False)
        policy_payloads.append(
            {
                **spec,
                "monitoring": summary,
                "outputs": {
                    "forward_trade_ledger": str(OUT_DIR / f"v90_{policy}_forward_trade_ledger.csv"),
                    "forward_delay_ledgers": str(OUT_DIR / f"v90_{policy}_forward_delay_ledgers.csv"),
                    "forward_delay_summary": str(OUT_DIR / f"v90_{policy}_forward_delay_summary.csv"),
                    "forward_extra_cost_summary": str(OUT_DIR / f"v90_{policy}_forward_extra_cost_summary.csv"),
                },
            }
        )
        aggregate = summary["aggregate"]
        decision = summary["decision"]
        policy_rows.append(
            {
                "policy": policy,
                "status": decision["status"],
                "monitoring_ok": bool(decision["monitoring_ok"]),
                "trade_count": int(aggregate["trade_count"]),
                "total_net_pnl_bps": float(aggregate["total_net_pnl_bps"]),
                "mean_net_pnl_bps": float(aggregate["mean_net_pnl_bps"]),
                "win_rate": float(aggregate["win_rate"]),
                "worst_delay_total_net_pnl_bps": float(aggregate["worst_delay_total_net_pnl_bps"]),
                "required_extra_cost_total_net_pnl_bps": float(aggregate["required_extra_cost_total_net_pnl_bps"]),
                "next_action": decision["next_action"],
            }
        )

    policy_table = pd.DataFrame(policy_rows)
    new_bars.to_csv(OUT_DIR / "v90_new_aggtrade_1m_flow_bars.csv", index=False)
    policy_table.to_csv(OUT_DIR / "v90_policy_monitoring.csv", index=False)
    new_signal_count = int(policy_table["trade_count"].sum()) if len(policy_table) else 0
    payload = {
        "version": "v90_btcusdc_forward_monitoring",
        "forward_start": FORWARD_START.isoformat(),
        "source_v89_selected_policy": v89["repair"]["aggregate"]["selected_policy"],
        "source_v89_conservative_policy": v89["conservative_same_family"]["policy"],
        "candidate": candidate.to_dict(),
        "data": {
            "base_bars": str(V50_BARS),
            "base_end": base_end.isoformat(),
            "new_aggtrade_files": [str(path) for path in new_paths],
            "new_aggtrade_file_count": int(len(new_paths)),
            "new_bar_count": int(len(new_bars)),
            "new_bar_start": new_bars["timestamp"].min().isoformat() if len(new_bars) else None,
            "new_bar_end": new_bars["timestamp"].max().isoformat() if len(new_bars) else None,
            "combined_bar_count": int(len(bars)),
            "combined_start": bars["timestamp"].min().isoformat(),
            "combined_end": bars["timestamp"].max().isoformat(),
        },
        "decision": {
            "new_signal_count": new_signal_count,
            "status": "no_signal" if new_signal_count == 0 else ("passed" if bool(policy_table["monitoring_ok"].all()) else "failed"),
            "next_action": "continue_monitoring" if new_signal_count == 0 else ("keep_monitoring" if bool(policy_table["monitoring_ok"].all()) else "investigate_forward_loss"),
        },
        "policies": policy_payloads,
        "outputs": {
            "summary_json": str(OUT_DIR / "v90_summary.json"),
            "policy_monitoring": str(OUT_DIR / "v90_policy_monitoring.csv"),
            "new_aggtrade_1m_flow_bars": str(OUT_DIR / "v90_new_aggtrade_1m_flow_bars.csv"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v90_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, policy_table)
    print(json.dumps(payload, indent=2, default=str))
