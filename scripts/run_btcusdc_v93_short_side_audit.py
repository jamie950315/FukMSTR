from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOURCE_LEDGER = (
    ROOT
    / "runs"
    / "research_v92_btcusdc_earliest_to_latest_window"
    / "v92_v89_conservative_same_family_-550_full_window_trade_ledger.csv"
)
OUT_DIR = ROOT / "runs" / "research_v93_btcusdc_short_side_audit"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V93_BTCUSDC_SHORT_SIDE_AUDIT_RESULTS.md"


def _prepare_trades(trades: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "signal", "net_pnl_bps"}
    missing = required.difference(trades.columns)
    if missing:
        raise ValueError(f"trades missing columns: {sorted(missing)}")
    frame = trades.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["signal"] = pd.to_numeric(frame["signal"], errors="coerce").fillna(0).astype(int)
    frame["net_pnl_bps"] = pd.to_numeric(frame["net_pnl_bps"], errors="coerce").fillna(0.0)
    frame = frame.loc[frame["signal"].isin([-1, 1])].sort_values("timestamp").reset_index(drop=True)
    frame["side"] = frame["signal"].map({1: "long", -1: "short"})
    frame["utc_hour"] = frame["timestamp"].dt.hour.astype(int)
    frame["taipei_hour"] = ((frame["utc_hour"] + 8) % 24).astype(int)
    frame["month"] = frame["timestamp"].dt.tz_convert(None).dt.to_period("M").astype(str)
    frame["quarter"] = frame["timestamp"].dt.tz_convert(None).dt.to_period("Q").astype(str)
    return frame


def _max_drawdown(pnl: pd.Series) -> float:
    equity = pd.to_numeric(pnl, errors="coerce").fillna(0.0).cumsum()
    return float((equity.cummax() - equity).max()) if len(equity) else 0.0


def _side_summary(trades: pd.DataFrame) -> pd.DataFrame:
    frame = _prepare_trades(trades)
    rows: list[dict[str, object]] = []
    total_pnl = float(frame["net_pnl_bps"].sum()) if len(frame) else 0.0
    total_trades = int(len(frame))
    for side, group in frame.groupby("side", sort=True):
        pnl = group["net_pnl_bps"]
        ts = group["timestamp"].sort_values().reset_index(drop=True)
        gaps = ts.diff().dropna().dt.total_seconds() / 86400.0
        month_totals = group.groupby("month", sort=True)["net_pnl_bps"].sum()
        active_months = month_totals.loc[month_totals != 0.0]
        rows.append(
            {
                "side": str(side),
                "trades": int(len(group)),
                "trade_share": float(len(group) / total_trades) if total_trades else 0.0,
                "total_net_pnl_bps": float(pnl.sum()),
                "pnl_share": float(pnl.sum() / total_pnl) if total_pnl else 0.0,
                "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                "win_rate": float((pnl > 0.0).mean()) if len(pnl) else 0.0,
                "max_drawdown_bps": _max_drawdown(pnl),
                "worst_trade_net_pnl_bps": float(pnl.min()) if len(pnl) else 0.0,
                "best_trade_net_pnl_bps": float(pnl.max()) if len(pnl) else 0.0,
                "first_trade": ts.min().isoformat() if len(ts) else None,
                "last_trade": ts.max().isoformat() if len(ts) else None,
                "mean_gap_days": float(gaps.mean()) if len(gaps) else 0.0,
                "median_gap_days": float(gaps.median()) if len(gaps) else 0.0,
                "p90_gap_days": float(gaps.quantile(0.90)) if len(gaps) else 0.0,
                "max_gap_days": float(gaps.max()) if len(gaps) else 0.0,
                "active_months": int(len(active_months)),
                "active_positive_month_rate": float((active_months > 0.0).mean()) if len(active_months) else 0.0,
                "worst_month_net_pnl_bps": float(active_months.min()) if len(active_months) else 0.0,
                "best_month_net_pnl_bps": float(active_months.max()) if len(active_months) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _bucket_summary(trades: pd.DataFrame, *, group_cols: list[str]) -> pd.DataFrame:
    frame = _prepare_trades(trades)
    rows = []
    for values, group in frame.groupby(group_cols, sort=True):
        if not isinstance(values, tuple):
            values = (values,)
        pnl = group["net_pnl_bps"]
        row = {col: value for col, value in zip(group_cols, values)}
        row.update(
            {
                "trades": int(len(group)),
                "total_net_pnl_bps": float(pnl.sum()),
                "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                "win_rate": float((pnl > 0.0).mean()) if len(pnl) else 0.0,
                "worst_trade_net_pnl_bps": float(pnl.min()) if len(pnl) else 0.0,
                "best_trade_net_pnl_bps": float(pnl.max()) if len(pnl) else 0.0,
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def _scenario_rows(trades: pd.DataFrame) -> pd.DataFrame:
    frame = _prepare_trades(trades)
    short = frame.loc[frame["side"] == "short"].copy()
    scenarios = [
        ("all_trades", frame),
        ("long_only", frame.loc[frame["side"] == "long"].copy()),
        ("short_only", short),
        ("remove_short_utc_13_17", frame.loc[~((frame["side"] == "short") & (frame["utc_hour"].isin([13, 17])))]),
        (
            "remove_short_2024q4_2025q1_2025q2",
            frame.loc[~((frame["side"] == "short") & (frame["quarter"].isin(["2024Q4", "2025Q1", "2025Q2"])))],
        ),
    ]
    rows = []
    for name, group in scenarios:
        pnl = group["net_pnl_bps"]
        rows.append(
            {
                "scenario": name,
                "trades": int(len(group)),
                "total_net_pnl_bps": float(pnl.sum()),
                "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                "win_rate": float((pnl > 0.0).mean()) if len(pnl) else 0.0,
                "max_drawdown_bps": _max_drawdown(pnl),
            }
        )
    return pd.DataFrame(rows)


def _write_report(payload: dict[str, object], tables: dict[str, pd.DataFrame]) -> None:
    lines = [
        "# Research V93 BTCUSDC Short-Side Audit Results",
        "",
        "## Decision",
        "",
        f"- Source policy: `{payload['source_policy']}`",
        f"- Source ledger: `{payload['source_ledger']}`",
        f"- Short-side verdict: `{payload['decision']['short_side_verdict']}`",
        f"- Main weakness: `{payload['decision']['main_weakness']}`",
        "",
        "## Side Summary",
        "",
        tables["side_summary"].to_csv(index=False).strip(),
        "",
        "## Scenario Comparison",
        "",
        tables["scenario_summary"].to_csv(index=False).strip(),
        "",
        "## Worst Short Months",
        "",
        tables["short_months"].sort_values("total_net_pnl_bps").head(10).to_csv(index=False).strip(),
        "",
        "## Short UTC Hour Summary",
        "",
        tables["short_hours"].sort_values("total_net_pnl_bps").to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "The short side is profitable, but it contributes less PnL than long while carrying larger drawdown. Its weakness is concentrated in specific historical regimes and UTC hours, not evenly spread across all short trades.",
        "",
        "This is an audit only. It does not promote a modified strategy or retune thresholds.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    trades = pd.read_csv(SOURCE_LEDGER)
    frame = _prepare_trades(trades)
    side_summary = _side_summary(frame)
    side_months = _bucket_summary(frame, group_cols=["side", "month"])
    side_quarters = _bucket_summary(frame, group_cols=["side", "quarter"])
    side_hours = _bucket_summary(frame, group_cols=["side", "utc_hour", "taipei_hour"])
    short_months = side_months.loc[side_months["side"] == "short"].copy()
    short_quarters = side_quarters.loc[side_quarters["side"] == "short"].copy()
    short_hours = side_hours.loc[side_hours["side"] == "short"].copy()
    scenario_summary = _scenario_rows(frame)

    side_summary.to_csv(OUT_DIR / "v93_side_summary.csv", index=False)
    side_months.to_csv(OUT_DIR / "v93_side_months.csv", index=False)
    side_quarters.to_csv(OUT_DIR / "v93_side_quarters.csv", index=False)
    side_hours.to_csv(OUT_DIR / "v93_side_hours.csv", index=False)
    short_months.to_csv(OUT_DIR / "v93_short_months.csv", index=False)
    short_quarters.to_csv(OUT_DIR / "v93_short_quarters.csv", index=False)
    short_hours.to_csv(OUT_DIR / "v93_short_hours.csv", index=False)
    scenario_summary.to_csv(OUT_DIR / "v93_scenario_summary.csv", index=False)

    short_row = side_summary.loc[side_summary["side"] == "short"].iloc[0].to_dict()
    long_row = side_summary.loc[side_summary["side"] == "long"].iloc[0].to_dict()
    payload = {
        "version": "v93_btcusdc_short_side_audit",
        "source_policy": "v89_conservative_same_family_-550",
        "source_ledger": str(SOURCE_LEDGER),
        "decision": {
            "short_side_verdict": "profitable_but_weaker_than_long",
            "main_weakness": "lower_mean_pnl_and_higher_drawdown_than_long",
            "short_total_net_pnl_bps": float(short_row["total_net_pnl_bps"]),
            "long_total_net_pnl_bps": float(long_row["total_net_pnl_bps"]),
            "short_max_drawdown_bps": float(short_row["max_drawdown_bps"]),
            "long_max_drawdown_bps": float(long_row["max_drawdown_bps"]),
        },
        "outputs": {
            "summary_json": str(OUT_DIR / "v93_summary.json"),
            "side_summary": str(OUT_DIR / "v93_side_summary.csv"),
            "side_months": str(OUT_DIR / "v93_side_months.csv"),
            "side_quarters": str(OUT_DIR / "v93_side_quarters.csv"),
            "side_hours": str(OUT_DIR / "v93_side_hours.csv"),
            "short_months": str(OUT_DIR / "v93_short_months.csv"),
            "short_quarters": str(OUT_DIR / "v93_short_quarters.csv"),
            "short_hours": str(OUT_DIR / "v93_short_hours.csv"),
            "scenario_summary": str(OUT_DIR / "v93_scenario_summary.csv"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v93_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(
        payload,
        {
            "side_summary": side_summary,
            "scenario_summary": scenario_summary,
            "short_months": short_months,
            "short_hours": short_hours,
        },
    )
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
