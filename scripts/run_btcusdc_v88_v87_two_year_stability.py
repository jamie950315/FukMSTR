from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import summarize_last_two_year_stability


ROOT = Path(__file__).resolve().parents[1]
V69_DIR = ROOT / "runs" / "research_v69_btcusdc_fixed_flow_hour_gate"
V87_DIR = ROOT / "runs" / "research_v87_btcusdc_recent_repair_validation"
OUT_DIR = ROOT / "runs" / "research_v88_btcusdc_v87_two_year_stability"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V88_BTCUSDC_V87_TWO_YEAR_STABILITY_RESULTS.md"

INPUT_LEDGER = V87_DIR / "v87_oversold_short_veto_trade_ledger.csv"
INPUT_DELAY_LEDGERS = V69_DIR / "v69_delay_trade_ledgers.csv"
OVERSOLD_SHORT_LOOKBACK_BPS = -650.0
EXTRA_COST_BPS = (0.0, 4.0, 8.0, 16.0)


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    out["hour"] = out["timestamp"].dt.hour.astype(int)
    out["net_pnl_bps"] = pd.to_numeric(out["net_pnl_bps"], errors="coerce").fillna(0.0)
    out["signal"] = pd.to_numeric(out["signal"], errors="coerce").fillna(0).astype(int)
    out["lookback_return_bps"] = pd.to_numeric(out["lookback_return_bps"], errors="coerce").fillna(0.0)
    return out.sort_values("timestamp").reset_index(drop=True)


def _v87_mask(frame: pd.DataFrame) -> pd.Series:
    return ~((frame["signal"] < 0) & (frame["lookback_return_bps"] < OVERSOLD_SHORT_LOOKBACK_BPS))


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


def _write_report(
    payload: dict[str, object],
    months: pd.DataFrame,
    quarters: pd.DataFrame,
    rolling: pd.DataFrame,
    delays: pd.DataFrame,
    extra: pd.DataFrame,
) -> None:
    aggregate = payload["aggregate"]
    month_summary = payload["months"]
    quarter_summary = payload["quarters"]
    decision = payload["decision"]
    rolling_summary = payload["rolling"]
    lines = [
        "# Research V88 BTCUSDC V87 Two-Year Stability Results",
        "",
        "## Decision",
        "",
        f"- Stable enough: `{decision['stable_enough']}`",
        f"- Failed checks: `{';'.join(decision['failed_checks'])}`",
        f"- Period: `{payload['period']['start_timestamp']}` to `{payload['period']['end_timestamp']}`",
        "",
        "## Aggregate",
        "",
        f"- Trades: `{aggregate['trade_count']}`",
        f"- Total net PnL: `{float(aggregate['total_net_pnl_bps']):.6f}` bps",
        f"- Mean net PnL: `{float(aggregate['mean_net_pnl_bps']):.6f}` bps",
        f"- Win rate: `{float(aggregate['win_rate']):.6f}`",
        f"- Max drawdown: `{float(aggregate['max_drawdown_bps']):.6f}` bps",
        f"- Worst trade: `{float(aggregate['worst_trade_net_pnl_bps']):.6f}` bps",
        f"- Best trade: `{float(aggregate['best_trade_net_pnl_bps']):.6f}` bps",
        f"- Worst delay total: `{float(aggregate['worst_delay_total_net_pnl_bps']):.6f}` bps",
        f"- Required extra cost +{float(aggregate['required_extra_cost_bps']):.1f} bps total: `{float(aggregate['required_extra_cost_total_net_pnl_bps']):.6f}` bps",
        "",
        "## Month Stability",
        "",
        f"- Calendar months: `{month_summary['calendar_month_count']}`",
        f"- Active months: `{month_summary['active_month_count']}`",
        f"- Calendar positive month rate: `{float(month_summary['calendar_positive_month_rate']):.6f}`",
        f"- Active positive month rate: `{float(month_summary['active_positive_month_rate']):.6f}`",
        f"- Worst month: `{float(month_summary['worst_month_net_pnl_bps']):.6f}` bps",
        f"- Best month: `{float(month_summary['best_month_net_pnl_bps']):.6f}` bps",
        "",
        "## Quarter Stability",
        "",
        f"- Quarters: `{quarter_summary['quarter_count']}`",
        f"- Positive quarter rate: `{float(quarter_summary['positive_quarter_rate']):.6f}`",
        f"- Worst quarter: `{float(quarter_summary['worst_quarter_net_pnl_bps']):.6f}` bps",
        f"- Best quarter: `{float(quarter_summary['best_quarter_net_pnl_bps']):.6f}` bps",
        "",
        "## Rolling Stability",
        "",
        f"- Rolling 3m positive rate: `{float(rolling_summary['rolling_3m']['positive_rate']):.6f}`; worst `{float(rolling_summary['rolling_3m']['worst_total_net_pnl_bps']):.6f}` bps",
        f"- Rolling 6m positive rate: `{float(rolling_summary['rolling_6m']['positive_rate']):.6f}`; worst `{float(rolling_summary['rolling_6m']['worst_total_net_pnl_bps']):.6f}` bps",
        f"- Rolling 12m positive rate: `{float(rolling_summary['rolling_12m']['positive_rate']):.6f}`; worst `{float(rolling_summary['rolling_12m']['worst_total_net_pnl_bps']):.6f}` bps",
        "",
        "## Months",
        "",
        months.to_csv(index=False).strip(),
        "",
        "## Quarters",
        "",
        quarters.to_csv(index=False).strip(),
        "",
        "## Rolling Windows",
        "",
        rolling.to_csv(index=False).strip(),
        "",
        "## Delay Stress",
        "",
        delays.to_csv(index=False).strip(),
        "",
        "## Extra Cost Stress",
        "",
        extra.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V88 applies the V87 oversold-short veto to the last two years of available BTCUSDC V69 fixed-flow history. The strategy remains profitable over the two-year window and passes delay, cost, drawdown, win-rate, and quarter-level checks.",
        "",
        "It does not pass the stricter stability gate because active month positivity and rolling 3/6-month positivity are below the required thresholds. The main weakness is a deep 2025Q4 drawdown cluster. This evidence is not strong enough to call the two-year stability high.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    if not INPUT_LEDGER.exists():
        raise SystemExit(f"missing input ledger: {INPUT_LEDGER}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    trades = _normalize(pd.read_csv(INPUT_LEDGER))
    end_ts = trades["timestamp"].max()
    start_ts = end_ts - pd.DateOffset(years=2)
    two_year_trades = trades.loc[(trades["timestamp"] >= start_ts) & (trades["timestamp"] <= end_ts)].copy().reset_index(drop=True)

    delay_ledgers = _normalize(pd.read_csv(INPUT_DELAY_LEDGERS))
    delay_ledgers = delay_ledgers.loc[_v87_mask(delay_ledgers)].copy()
    delay_ledgers = delay_ledgers.loc[(delay_ledgers["timestamp"] >= start_ts) & (delay_ledgers["timestamp"] <= end_ts)].copy().reset_index(drop=True)
    delays = _delay_summary(delay_ledgers)
    extra = _extra_cost_summary(two_year_trades)

    result = summarize_last_two_year_stability(
        trades,
        delay_summary=delays,
        extra_cost_summary=extra,
        start_timestamp=start_ts,
        end_timestamp=end_ts,
    )
    months = pd.DataFrame(result["months"]["rows"])
    quarters = pd.DataFrame(result["quarters"]["rows"])
    rolling = pd.DataFrame(result["rolling"]["rows"])
    two_year_trades.to_csv(OUT_DIR / "v88_two_year_trade_ledger.csv", index=False)
    delay_ledgers.to_csv(OUT_DIR / "v88_two_year_delay_trade_ledgers.csv", index=False)
    delays.to_csv(OUT_DIR / "v88_two_year_delay_summary.csv", index=False)
    extra.to_csv(OUT_DIR / "v88_two_year_extra_cost_summary.csv", index=False)
    months.to_csv(OUT_DIR / "v88_two_year_months.csv", index=False)
    quarters.to_csv(OUT_DIR / "v88_two_year_quarters.csv", index=False)
    rolling.to_csv(OUT_DIR / "v88_two_year_rolling_windows.csv", index=False)
    payload = {
        "version": "v88_btcusdc_v87_two_year_stability",
        "input_ledger": str(INPUT_LEDGER),
        "policy": "oversold_short_veto",
        "policy_description": f"Skip short trades after a 24h lookback move below {OVERSOLD_SHORT_LOOKBACK_BPS:.0f} bps.",
        **result,
        "outputs": {
            "summary_json": str(OUT_DIR / "v88_summary.json"),
            "two_year_trade_ledger": str(OUT_DIR / "v88_two_year_trade_ledger.csv"),
            "two_year_delay_trade_ledgers": str(OUT_DIR / "v88_two_year_delay_trade_ledgers.csv"),
            "two_year_delay_summary": str(OUT_DIR / "v88_two_year_delay_summary.csv"),
            "two_year_extra_cost_summary": str(OUT_DIR / "v88_two_year_extra_cost_summary.csv"),
            "two_year_months": str(OUT_DIR / "v88_two_year_months.csv"),
            "two_year_quarters": str(OUT_DIR / "v88_two_year_quarters.csv"),
            "two_year_rolling_windows": str(OUT_DIR / "v88_two_year_rolling_windows.csv"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v88_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, months, quarters, rolling, delays, extra)
    print(json.dumps(payload, indent=2, default=str))
