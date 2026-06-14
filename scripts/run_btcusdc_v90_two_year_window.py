from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import summarize_last_two_year_stability

import run_btcusdc_v90_forward_monitoring as v90


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v90_btcusdc_two_year_window"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V90_BTCUSDC_TWO_YEAR_WINDOW_RESULTS.md"


def _write_report(payload: dict[str, object], policy_table: pd.DataFrame) -> None:
    lines = [
        "# Research V90 BTCUSDC Two-Year Window Results",
        "",
        "## Decision",
        "",
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
        "This run applies the V90 data-refresh and fixed-policy reconstruction path to the most recent two years ending at the extended data end. It does not retune thresholds.",
        "",
        "The result should be read as an updated two-year replay of the V69/V87/V89 policy variants, not as a new forward-trade proof.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    base_bars = v90._load_base_bars(v90.V50_BARS)
    base_end = base_bars["timestamp"].max()
    new_paths = v90._new_aggtrade_paths(base_end)
    bars, new_bars = v90._combined_bars(base_bars, new_paths)
    candidate = v90._candidate()
    v69 = json.loads(v90.V69_SUMMARY.read_text(encoding="utf-8"))
    excluded_hours = [int(hour) for hour in v69["hour_gate"]["excluded_hours"]]
    end_ts = bars["timestamp"].max()
    start_ts = end_ts - pd.DateOffset(years=2)
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
            "description": "V69 hour gate plus V89 mechanical removal of UTC hours 0, 2, 3, and 4 on top of the V87 short veto.",
        },
    ]

    ledgers: dict[int, pd.DataFrame] = {}
    for delay in v90.ENTRY_DELAYS:
        ledgers[int(delay)] = v90._normalize_ledger(v90.build_delayed_candidate_trade_ledger(bars, candidate, entry_delay_minutes=int(delay)))

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

        delay_summary = v90._delay_summary(scoped_delay)
        extra = v90._extra_cost_summary(scoped_primary)
        stability = summarize_last_two_year_stability(
            kept_primary,
            delay_summary=delay_summary,
            extra_cost_summary=extra,
            start_timestamp=start_ts,
            end_timestamp=end_ts,
        )
        months = pd.DataFrame(stability["months"]["rows"])
        rolling = pd.DataFrame(stability["rolling"]["rows"])
        scoped_primary.to_csv(OUT_DIR / f"v90_{policy}_two_year_trade_ledger.csv", index=False)
        scoped_delay.to_csv(OUT_DIR / f"v90_{policy}_two_year_delay_ledgers.csv", index=False)
        delay_summary.to_csv(OUT_DIR / f"v90_{policy}_two_year_delay_summary.csv", index=False)
        extra.to_csv(OUT_DIR / f"v90_{policy}_two_year_extra_cost_summary.csv", index=False)
        months.to_csv(OUT_DIR / f"v90_{policy}_two_year_months.csv", index=False)
        rolling.to_csv(OUT_DIR / f"v90_{policy}_two_year_rolling_windows.csv", index=False)

        aggregate = stability["aggregate"]
        month_summary = stability["months"]
        rolling_summary = stability["rolling"]
        decision = stability["decision"]
        policy_payloads.append(
            {
                **spec,
                "stability": stability,
                "outputs": {
                    "two_year_trade_ledger": str(OUT_DIR / f"v90_{policy}_two_year_trade_ledger.csv"),
                    "two_year_delay_ledgers": str(OUT_DIR / f"v90_{policy}_two_year_delay_ledgers.csv"),
                    "two_year_delay_summary": str(OUT_DIR / f"v90_{policy}_two_year_delay_summary.csv"),
                    "two_year_extra_cost_summary": str(OUT_DIR / f"v90_{policy}_two_year_extra_cost_summary.csv"),
                    "two_year_months": str(OUT_DIR / f"v90_{policy}_two_year_months.csv"),
                    "two_year_rolling_windows": str(OUT_DIR / f"v90_{policy}_two_year_rolling_windows.csv"),
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
    policy_table.to_csv(OUT_DIR / "v90_two_year_policy_table.csv", index=False)
    new_bars.to_csv(OUT_DIR / "v90_two_year_new_aggtrade_1m_flow_bars.csv", index=False)

    payload = {
        "version": "v90_btcusdc_two_year_window",
        "candidate": candidate.to_dict(),
        "period": {
            "start_timestamp": start_ts.isoformat(),
            "end_timestamp": end_ts.isoformat(),
        },
        "data": {
            "base_bars": str(v90.V50_BARS),
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
            "policy_count": int(len(policy_table)),
            "stable_policy_count": int(policy_table["stable_enough"].astype(bool).sum()),
            "best_stable_policy": best_stable_policy,
        },
        "policies": policy_payloads,
        "outputs": {
            "summary_json": str(OUT_DIR / "v90_two_year_summary.json"),
            "policy_table": str(OUT_DIR / "v90_two_year_policy_table.csv"),
            "new_aggtrade_1m_flow_bars": str(OUT_DIR / "v90_two_year_new_aggtrade_1m_flow_bars.csv"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v90_two_year_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, policy_table)
    print(json.dumps(payload, indent=2, default=str))
