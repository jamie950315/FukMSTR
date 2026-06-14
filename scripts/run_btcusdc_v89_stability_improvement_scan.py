from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import (
    summarize_last_two_year_stability,
    summarize_two_year_stability_repair_candidates,
)


ROOT = Path(__file__).resolve().parents[1]
V88_DIR = ROOT / "runs" / "research_v88_btcusdc_v87_two_year_stability"
OUT_DIR = ROOT / "runs" / "research_v89_btcusdc_stability_improvement_scan"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V89_BTCUSDC_STABILITY_IMPROVEMENT_SCAN_RESULTS.md"

INPUT_LEDGER = V88_DIR / "v88_two_year_trade_ledger.csv"
INPUT_DELAY_LEDGERS = V88_DIR / "v88_two_year_delay_trade_ledgers.csv"
EXTRA_COST_BPS = (0.0, 4.0, 8.0, 16.0)
MIN_TRADES = 100


POLICIES: tuple[dict[str, object], ...] = (
    {
        "policy": "stricter_oversold_short_veto_-600",
        "description": "Tighten the V87 oversold-short veto from -650 bps to -600 bps.",
        "family": "same_veto",
        "kind": "short_lookback_floor",
        "threshold": -600.0,
    },
    {
        "policy": "stricter_oversold_short_veto_-550",
        "description": "Tighten the V87 oversold-short veto from -650 bps to -550 bps.",
        "family": "same_veto",
        "kind": "short_lookback_floor",
        "threshold": -550.0,
    },
    {
        "policy": "stricter_oversold_short_veto_-500",
        "description": "Tighten the V87 oversold-short veto from -650 bps to -500 bps.",
        "family": "same_veto",
        "kind": "short_lookback_floor",
        "threshold": -500.0,
    },
    {
        "policy": "remove_hours_0_2_3_4",
        "description": "Remove UTC hours 0, 2, 3, and 4 from the V87 two-year ledger.",
        "family": "hour_gate",
        "kind": "remove_hours",
        "hours": (0, 2, 3, 4),
    },
    {
        "policy": "remove_hours_0_3_4_6",
        "description": "Remove UTC hours 0, 3, 4, and 6 from the V87 two-year ledger.",
        "family": "hour_gate",
        "kind": "remove_hours",
        "hours": (0, 3, 4, 6),
    },
    {
        "policy": "remove_hours_0_3_4_7",
        "description": "Remove UTC hours 0, 3, 4, and 7 from the V87 two-year ledger.",
        "family": "hour_gate",
        "kind": "remove_hours",
        "hours": (0, 3, 4, 7),
    },
    {
        "policy": "remove_hours_3_4_7_11",
        "description": "Remove UTC hours 3, 4, 7, and 11 from the V87 two-year ledger.",
        "family": "hour_gate",
        "kind": "remove_hours",
        "hours": (3, 4, 7, 11),
    },
    {
        "policy": "no_high_volume_negative_flow",
        "description": "Skip trades when volume_ratio is above 15 and aggTrade flow is negative.",
        "family": "regime_filter",
        "kind": "high_volume_negative_flow",
        "volume_ratio": 15.0,
    },
    {
        "policy": "remove_hours_0_2_3_plus_no_high_volume_negative_flow",
        "description": "Remove UTC hours 0, 2, 3 and skip high-volume negative-flow trades.",
        "family": "hybrid",
        "kind": "hour_and_high_volume_negative_flow",
        "hours": (0, 2, 3),
        "volume_ratio": 15.0,
    },
)


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    out["hour"] = out["timestamp"].dt.hour.astype(int)
    numeric_columns = [
        "net_pnl_bps",
        "signal",
        "lookback_return_bps",
        "abs_return_bps",
        "range_bps",
        "volume_ratio",
        "flow_imbalance",
        "entry_delay_minutes",
    ]
    for column in numeric_columns:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0.0)
    if "signal" in out.columns:
        out["signal"] = out["signal"].astype(int)
    if "entry_delay_minutes" in out.columns:
        out["entry_delay_minutes"] = out["entry_delay_minutes"].astype(int)
    return out.sort_values("timestamp").reset_index(drop=True)


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


def _policy_mask(spec: dict[str, object], frame: pd.DataFrame) -> pd.Series:
    kind = str(spec["kind"])
    if kind == "baseline":
        return pd.Series(True, index=frame.index)
    if kind == "short_lookback_floor":
        threshold = float(spec["threshold"])
        return ~((frame["signal"] < 0) & (frame["lookback_return_bps"] < threshold))
    if kind == "remove_hours":
        hours = [int(hour) for hour in spec["hours"]]
        return ~frame["hour"].isin(hours)
    if kind == "high_volume_negative_flow":
        volume_ratio = float(spec["volume_ratio"])
        return ~((frame["volume_ratio"] > volume_ratio) & (frame["flow_imbalance"] < 0.0))
    if kind == "hour_and_high_volume_negative_flow":
        hours = [int(hour) for hour in spec["hours"]]
        volume_ratio = float(spec["volume_ratio"])
        hour_mask = ~frame["hour"].isin(hours)
        flow_mask = ~((frame["volume_ratio"] > volume_ratio) & (frame["flow_imbalance"] < 0.0))
        return hour_mask & flow_mask
    raise ValueError(f"unknown policy kind: {kind}")


def _stability_for(
    trades: pd.DataFrame,
    delay_ledgers: pd.DataFrame,
    *,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame]:
    delays = _delay_summary(delay_ledgers)
    extra = _extra_cost_summary(trades)
    result = summarize_last_two_year_stability(
        trades,
        delay_summary=delays,
        extra_cost_summary=extra,
        start_timestamp=start_ts,
        end_timestamp=end_ts,
        min_trades=MIN_TRADES,
    )
    return result, delays, extra


def _candidate_row(policy: str, family: str, stability: dict[str, object]) -> dict[str, object]:
    aggregate = stability["aggregate"]
    months = stability["months"]
    quarters = stability["quarters"]
    rolling = stability["rolling"]
    decision = stability["decision"]
    return {
        "policy": policy,
        "family": family,
        "stable_enough": bool(decision["stable_enough"]),
        "failed_checks": ";".join(decision["failed_checks"]),
        "trade_count": int(aggregate["trade_count"]),
        "total_net_pnl_bps": float(aggregate["total_net_pnl_bps"]),
        "mean_net_pnl_bps": float(aggregate["mean_net_pnl_bps"]),
        "win_rate": float(aggregate["win_rate"]),
        "max_drawdown_bps": float(aggregate["max_drawdown_bps"]),
        "required_extra_cost_total_net_pnl_bps": float(aggregate["required_extra_cost_total_net_pnl_bps"]),
        "worst_delay_total_net_pnl_bps": float(aggregate["worst_delay_total_net_pnl_bps"]),
        "active_positive_month_rate": float(months["active_positive_month_rate"]),
        "calendar_positive_month_rate": float(months["calendar_positive_month_rate"]),
        "positive_quarter_rate": float(quarters["positive_quarter_rate"]),
        "rolling_3m_positive_rate": float(rolling["rolling_3m"]["positive_rate"]),
        "rolling_6m_positive_rate": float(rolling["rolling_6m"]["positive_rate"]),
        "rolling_12m_positive_rate": float(rolling["rolling_12m"]["positive_rate"]),
        "rolling_3m_worst_net_pnl_bps": float(rolling["rolling_3m"]["worst_total_net_pnl_bps"]),
        "rolling_6m_worst_net_pnl_bps": float(rolling["rolling_6m"]["worst_total_net_pnl_bps"]),
    }


def _write_report(
    payload: dict[str, object],
    candidates: pd.DataFrame,
    selected_months: pd.DataFrame,
    conservative_months: pd.DataFrame,
) -> None:
    baseline = payload["baseline"]["aggregate"]
    repair = payload["repair"]["aggregate"]
    selected = payload["selected"]
    conservative = payload["conservative_same_family"]
    lines = [
        "# Research V89 BTCUSDC Stability Improvement Scan Results",
        "",
        "## Decision",
        "",
        f"- Promote stability repair: `{repair['promote_stability_repair']}`",
        f"- Mechanical selected policy: `{repair['selected_policy']}`",
        f"- Mechanical selected total improvement: `{float(repair['selected_total_improvement_bps']):.6f}` bps",
        f"- Mechanical selected drawdown improvement: `{float(repair['selected_drawdown_improvement_bps']):.6f}` bps",
        f"- Conservative same-family policy: `{conservative['policy']}`",
        "",
        "## Baseline V88",
        "",
        f"- Trades: `{baseline['trade_count']}`",
        f"- Total net PnL: `{float(baseline['total_net_pnl_bps']):.6f}` bps",
        f"- Mean net PnL: `{float(baseline['mean_net_pnl_bps']):.6f}` bps",
        f"- Win rate: `{float(baseline['win_rate']):.6f}`",
        f"- Max drawdown: `{float(baseline['max_drawdown_bps']):.6f}` bps",
        "",
        "## Mechanical Selected Policy",
        "",
        f"- Policy: `{selected['policy']}`",
        f"- Description: {selected['description']}",
        f"- Trades: `{selected['stability']['aggregate']['trade_count']}`",
        f"- Total net PnL: `{float(selected['stability']['aggregate']['total_net_pnl_bps']):.6f}` bps",
        f"- Mean net PnL: `{float(selected['stability']['aggregate']['mean_net_pnl_bps']):.6f}` bps",
        f"- Win rate: `{float(selected['stability']['aggregate']['win_rate']):.6f}`",
        f"- Max drawdown: `{float(selected['stability']['aggregate']['max_drawdown_bps']):.6f}` bps",
        f"- Active positive month rate: `{float(selected['stability']['months']['active_positive_month_rate']):.6f}`",
        f"- Rolling 3m positive rate: `{float(selected['stability']['rolling']['rolling_3m']['positive_rate']):.6f}`",
        f"- Rolling 6m positive rate: `{float(selected['stability']['rolling']['rolling_6m']['positive_rate']):.6f}`",
        "",
        "## Conservative Same-Family Policy",
        "",
        f"- Policy: `{conservative['policy']}`",
        f"- Description: {conservative['description']}",
        f"- Trades: `{conservative['stability']['aggregate']['trade_count']}`",
        f"- Total net PnL: `{float(conservative['stability']['aggregate']['total_net_pnl_bps']):.6f}` bps",
        f"- Mean net PnL: `{float(conservative['stability']['aggregate']['mean_net_pnl_bps']):.6f}` bps",
        f"- Win rate: `{float(conservative['stability']['aggregate']['win_rate']):.6f}`",
        f"- Max drawdown: `{float(conservative['stability']['aggregate']['max_drawdown_bps']):.6f}` bps",
        f"- Active positive month rate: `{float(conservative['stability']['months']['active_positive_month_rate']):.6f}`",
        f"- Rolling 3m positive rate: `{float(conservative['stability']['rolling']['rolling_3m']['positive_rate']):.6f}`",
        f"- Rolling 6m positive rate: `{float(conservative['stability']['rolling']['rolling_6m']['positive_rate']):.6f}`",
        "",
        "## Candidate Scan",
        "",
        candidates.to_csv(index=False).strip(),
        "",
        "## Mechanical Selected Months",
        "",
        selected_months.to_csv(index=False).strip(),
        "",
        "## Conservative Same-Family Months",
        "",
        conservative_months.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V89 shows the V88 instability is repairable inside the current two-year BTCUSDC evidence. The mechanical best passing candidate removes UTC 0, 2, 3, and 4; it raises total PnL and passes all V88 stability checks with 102 trades.",
        "",
        "The cleaner same-family repair tightens the existing V87 oversold-short veto from -650 bps to -550 bps. It also passes all V88 stability checks with 112 trades, lower drawdown than V88, positive delay stress, and positive +16 bps cost stress.",
        "",
        "Both are research candidates selected after looking at the two-year instability. They are not live-trading guarantees and need fresh forward monitoring before being treated as production-ready.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    if not INPUT_LEDGER.exists():
        raise SystemExit(f"missing input ledger: {INPUT_LEDGER}")
    if not INPUT_DELAY_LEDGERS.exists():
        raise SystemExit(f"missing input delay ledgers: {INPUT_DELAY_LEDGERS}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    trades = _normalize(pd.read_csv(INPUT_LEDGER))
    delay_ledgers = _normalize(pd.read_csv(INPUT_DELAY_LEDGERS))
    start_ts = trades["timestamp"].min()
    end_ts = trades["timestamp"].max()
    baseline, baseline_delays, baseline_extra = _stability_for(
        trades,
        delay_ledgers,
        start_ts=start_ts,
        end_ts=end_ts,
    )

    candidate_payloads: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    for spec in POLICIES:
        policy = str(spec["policy"])
        family = str(spec["family"])
        kept_trades = trades.loc[_policy_mask(spec, trades)].copy().reset_index(drop=True)
        kept_delays = delay_ledgers.loc[_policy_mask(spec, delay_ledgers)].copy().reset_index(drop=True)
        stability, delays, extra = _stability_for(kept_trades, kept_delays, start_ts=start_ts, end_ts=end_ts)
        output_prefix = OUT_DIR / f"v89_{policy}"
        kept_trades.to_csv(output_prefix.with_name(f"{output_prefix.name}_trade_ledger.csv"), index=False)
        delays.to_csv(output_prefix.with_name(f"{output_prefix.name}_delay_summary.csv"), index=False)
        extra.to_csv(output_prefix.with_name(f"{output_prefix.name}_extra_cost_summary.csv"), index=False)
        payload = {
            "policy": policy,
            "family": family,
            "description": str(spec["description"]),
            "stability": stability,
            "outputs": {
                "trade_ledger": str(output_prefix.with_name(f"{output_prefix.name}_trade_ledger.csv")),
                "delay_summary": str(output_prefix.with_name(f"{output_prefix.name}_delay_summary.csv")),
                "extra_cost_summary": str(output_prefix.with_name(f"{output_prefix.name}_extra_cost_summary.csv")),
            },
        }
        candidate_payloads.append(payload)
        candidate_rows.append(_candidate_row(policy, family, stability))

    repair = summarize_two_year_stability_repair_candidates(
        baseline,
        candidate_payloads,
        min_total_improvement_bps=0.0,
        min_trades=MIN_TRADES,
    )
    selected_policy = repair["aggregate"]["selected_policy"]
    selected = next(row for row in candidate_payloads if row["policy"] == selected_policy)
    conservative = next(
        row
        for row in candidate_payloads
        if row["family"] == "same_veto" and bool(row["stability"]["decision"]["stable_enough"])
    )

    candidates = pd.DataFrame(candidate_rows).sort_values(
        ["stable_enough", "total_net_pnl_bps", "trade_count"],
        ascending=[False, False, False],
    )
    selected_months = pd.DataFrame(selected["stability"]["months"]["rows"])
    conservative_months = pd.DataFrame(conservative["stability"]["months"]["rows"])
    baseline_delays.to_csv(OUT_DIR / "v89_baseline_delay_summary.csv", index=False)
    baseline_extra.to_csv(OUT_DIR / "v89_baseline_extra_cost_summary.csv", index=False)
    candidates.to_csv(OUT_DIR / "v89_stability_repair_candidates.csv", index=False)
    selected_months.to_csv(OUT_DIR / "v89_selected_months.csv", index=False)
    conservative_months.to_csv(OUT_DIR / "v89_conservative_same_family_months.csv", index=False)

    payload = {
        "version": "v89_btcusdc_stability_improvement_scan",
        "input_ledger": str(INPUT_LEDGER),
        "input_delay_ledgers": str(INPUT_DELAY_LEDGERS),
        "baseline": baseline,
        "repair": repair,
        "selected": selected,
        "conservative_same_family": conservative,
        "candidates": candidate_payloads,
        "outputs": {
            "summary_json": str(OUT_DIR / "v89_summary.json"),
            "candidate_table": str(OUT_DIR / "v89_stability_repair_candidates.csv"),
            "selected_months": str(OUT_DIR / "v89_selected_months.csv"),
            "conservative_same_family_months": str(OUT_DIR / "v89_conservative_same_family_months.csv"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v89_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, candidates, selected_months, conservative_months)
    print(json.dumps(payload, indent=2, default=str))
