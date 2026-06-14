from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v139_indicator_leverage"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V139_BTCUSDC_INDICATOR_LEVERAGE.md"
V138_SUMMARY = ROOT / "runs" / "research_v138_btcusdc_live_confidence_sized_model" / "v138_live_confidence_sized_model_summary.json"
V138_SELECTED_TRADES = ROOT / "runs" / "research_v138_btcusdc_live_confidence_sized_model" / "v138_selected_trades.csv"
V138_SIZED_RESCUE_EVENTS = ROOT / "runs" / "research_v138_btcusdc_live_confidence_sized_model" / "v138_sized_rescue_events.csv"

DEFAULT_ACCOUNT_LEVERAGE = 1.0
INDICATOR_ACCOUNT_LEVERAGE = {
    "rescue_high_ge_0p66": 5.0,
    "v123_threshold": 1.5,
}
FIXED_LEVERAGE_VALUES = (1.0, 2.0, 3.0, 4.0, 5.0)
MAX_SELECTED_DRAWDOWN_PCT = -20.0
REQUIRED_POSITIVE_MONTHS = 24


def _strategy_config() -> dict[str, object]:
    return {
        "base": "v138_btcusdc_live_confidence_sized_model",
        "default_account_leverage": DEFAULT_ACCOUNT_LEVERAGE,
        "indicator_account_leverage": dict(INDICATOR_ACCOUNT_LEVERAGE),
        "max_selected_drawdown_pct": MAX_SELECTED_DRAWDOWN_PCT,
        "required_positive_months": REQUIRED_POSITIVE_MONTHS,
        "uses_indicator_leverage": True,
        "uses_new_trade_filter": False,
        "uses_daily_trade_cap": False,
        "uses_day_end_ranking": False,
        "leverage_scope": "account_return_overlay",
    }


def _load_v138_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    trades = pd.read_csv(V138_SELECTED_TRADES)
    rescue = pd.read_csv(V138_SIZED_RESCUE_EVENTS)
    trades["timestamp"] = pd.to_datetime(trades["timestamp"], utc=True)
    rescue["timestamp"] = pd.to_datetime(rescue["timestamp"], utc=True)
    return trades, rescue


def _enrich_indicator_columns(trades: pd.DataFrame, rescue_events: pd.DataFrame) -> pd.DataFrame:
    frame = trades.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    rescue = rescue_events.copy()
    rescue["timestamp"] = pd.to_datetime(rescue["timestamp"], utc=True)
    rescue_cols = ["timestamp", "direction_probability", "signal", "prob_up", "prob_down"]
    enriched = frame.merge(rescue[rescue_cols], on="timestamp", how="left")
    enriched["indicator_source"] = enriched["leg"].astype(str) + ":" + enriched["source"].astype(str)
    enriched["indicator_key"] = enriched["source"].astype(str)

    rescue_mask = enriched["leg"].astype(str).eq("rescue")
    probability = pd.to_numeric(enriched["direction_probability"], errors="coerce")
    enriched.loc[rescue_mask & probability.lt(0.62), "indicator_key"] = "rescue_low_0p60_0p62"
    enriched.loc[rescue_mask & probability.ge(0.62) & probability.lt(0.66), "indicator_key"] = "rescue_mid_0p62_0p66"
    enriched.loc[rescue_mask & probability.ge(0.66), "indicator_key"] = "rescue_high_ge_0p66"
    enriched["weighted_net_pnl_bps"] = pd.to_numeric(enriched["weighted_net_pnl_bps"], errors="coerce").fillna(0.0)
    enriched["position_weight"] = pd.to_numeric(enriched["position_weight"], errors="coerce").fillna(0.0)
    return enriched.sort_values(["timestamp", "leg", "source"], kind="mergesort").reset_index(drop=True)


def _indicator_summary(frame: pd.DataFrame, group_col: str) -> pd.DataFrame:
    work = frame.copy()
    work["is_win"] = pd.to_numeric(work["weighted_net_pnl_bps"], errors="coerce").fillna(0.0).gt(0.0)
    grouped = (
        work.groupby(group_col, dropna=False)
        .agg(
            trade_count=("weighted_net_pnl_bps", "size"),
            total_net_pnl_bps=("weighted_net_pnl_bps", "sum"),
            mean_net_pnl_bps=("weighted_net_pnl_bps", "mean"),
            win_rate=("is_win", "mean"),
            avg_position_weight=("position_weight", "mean"),
        )
        .reset_index()
    )
    monthly = work.groupby([group_col, "month"], dropna=False)["weighted_net_pnl_bps"].sum().reset_index()
    month_summary = (
        monthly.groupby(group_col, dropna=False)
        .agg(
            positive_months=("weighted_net_pnl_bps", lambda s: int((s > 0.0).sum())),
            month_count=("weighted_net_pnl_bps", "size"),
            worst_month_bps=("weighted_net_pnl_bps", "min"),
        )
        .reset_index()
    )
    return (
        grouped.merge(month_summary, on=group_col, how="left")
        .sort_values(["total_net_pnl_bps", "win_rate"], ascending=[False, False])
        .reset_index(drop=True)
    )


def _apply_indicator_leverage(
    trades: pd.DataFrame,
    *,
    leverage_map: dict[str, float],
    default_leverage: float,
) -> pd.DataFrame:
    out = trades.copy()
    out["account_leverage"] = out["indicator_key"].map(leverage_map).fillna(float(default_leverage)).astype(float)
    out["account_pnl_bps"] = pd.to_numeric(out["weighted_net_pnl_bps"], errors="coerce").fillna(0.0) * out["account_leverage"]
    out["account_return_pct"] = out["account_pnl_bps"] / 100.0
    out["equity_return_pct"] = out["account_return_pct"].cumsum()
    out["drawdown_pct"] = out["equity_return_pct"] - out["equity_return_pct"].cummax()
    return out


def _summarize_account_path(policy: str, path: pd.DataFrame) -> dict[str, object]:
    if path.empty:
        return {
            "policy": policy,
            "trade_count": 0,
            "total_account_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "positive_months": 0,
            "month_count": 0,
            "worst_month_pct": 0.0,
            "avg_account_leverage": 0.0,
            "max_account_leverage": 0.0,
            "levered_win_rate": 0.0,
        }
    monthly = path.groupby("month", sort=True)["account_return_pct"].sum()
    return {
        "policy": policy,
        "trade_count": int(len(path)),
        "total_account_return_pct": float(path["account_return_pct"].sum()),
        "max_drawdown_pct": float(path["drawdown_pct"].min()),
        "positive_months": int((monthly > 0.0).sum()),
        "month_count": int(len(monthly)),
        "worst_month_pct": float(monthly.min()),
        "avg_account_leverage": float(path["account_leverage"].mean()),
        "max_account_leverage": float(path["account_leverage"].max()),
        "levered_win_rate": float((path["account_pnl_bps"] > 0.0).mean()),
    }


def _fixed_leverage_comparison(enriched: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    keys = list(enriched["indicator_key"].dropna().unique())
    for leverage in FIXED_LEVERAGE_VALUES:
        path = _apply_indicator_leverage(
            enriched,
            leverage_map={key: float(leverage) for key in keys},
            default_leverage=float(leverage),
        )
        row = _summarize_account_path(f"fixed_{leverage:g}x", path)
        row["fixed_leverage"] = float(leverage)
        rows.append(row)
    return pd.DataFrame(rows)


def _scan_indicator_leverage(enriched: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for v122 in (1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0):
        for rescue_high in (1.0, 1.5, 2.0, 3.0, 4.0, 5.0):
            for rescue_mid in (1.0, 1.25, 1.5, 2.0, 2.5):
                for rescue_low in (1.0, 1.25, 1.5, 2.0):
                    for v123 in (1.0, 1.25, 1.5, 2.0, 2.5):
                        leverage_map = {
                            "v122_drought": v122,
                            "rescue_high_ge_0p66": rescue_high,
                            "rescue_mid_0p62_0p66": rescue_mid,
                            "rescue_low_0p60_0p62": rescue_low,
                            "v123_threshold": v123,
                        }
                        path = _apply_indicator_leverage(
                            enriched,
                            leverage_map=leverage_map,
                            default_leverage=DEFAULT_ACCOUNT_LEVERAGE,
                        )
                        row = _summarize_account_path("scan", path)
                        row.update(leverage_map)
                        row["passes_risk_gate"] = (
                            int(row["positive_months"]) >= REQUIRED_POSITIVE_MONTHS
                            and int(row["month_count"]) >= REQUIRED_POSITIVE_MONTHS
                            and float(row["max_drawdown_pct"]) >= MAX_SELECTED_DRAWDOWN_PCT
                            and float(row["worst_month_pct"]) > 0.0
                            and float(row["total_account_return_pct"]) > 0.0
                        )
                        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        ["passes_risk_gate", "total_account_return_pct", "max_drawdown_pct"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def _passes_v139_gate(row: dict[str, object], *, v138_total_account_return_pct: float) -> bool:
    return (
        float(row.get("total_account_return_pct", 0.0)) > float(v138_total_account_return_pct)
        and float(row.get("max_drawdown_pct", -999.0)) >= MAX_SELECTED_DRAWDOWN_PCT
        and int(row.get("positive_months", 0)) >= REQUIRED_POSITIVE_MONTHS
        and int(row.get("month_count", 0)) >= REQUIRED_POSITIVE_MONTHS
        and float(row.get("worst_month_pct", 0.0)) > 0.0
    )


def _write_report(
    payload: dict[str, object],
    indicator_source_summary: pd.DataFrame,
    indicator_key_summary: pd.DataFrame,
    selected_path: pd.DataFrame,
    fixed_leverage: pd.DataFrame,
    scan: pd.DataFrame,
) -> None:
    selected = payload["selected"]
    comparison = payload["comparison"]
    monthly = selected_path.groupby("month", sort=True)["account_return_pct"].sum().reset_index()
    leverage_by_key = (
        selected_path.groupby("indicator_key", sort=True)
        .agg(
            trade_count=("account_pnl_bps", "size"),
            account_return_pct=("account_return_pct", "sum"),
            win_rate=("account_pnl_bps", lambda s: (s > 0.0).mean()),
            avg_account_leverage=("account_leverage", "mean"),
        )
        .reset_index()
        .sort_values("account_return_pct", ascending=False)
    )
    top_scan_cols = [
        "v122_drought",
        "rescue_high_ge_0p66",
        "rescue_mid_0p62_0p66",
        "rescue_low_0p60_0p62",
        "v123_threshold",
        "total_account_return_pct",
        "max_drawdown_pct",
        "positive_months",
        "worst_month_pct",
        "passes_risk_gate",
    ]
    lines = [
        "# Research V139 BTCUSDC Indicator Leverage",
        "",
        "## Decision",
        "",
        f"- V138 1x account return: `{comparison['v138_account_return_pct']:.6f}%`",
        f"- V138 max drawdown at 1x: `{comparison['v138_account_max_drawdown_pct']:.6f}%`",
        f"- V139 selected account return: `{selected['total_account_return_pct']:.6f}%`",
        f"- V139 selected max drawdown: `{selected['max_drawdown_pct']:.6f}%`",
        f"- Trade count: `{selected['trade_count']}`",
        f"- Positive months: `{selected['positive_months']}/{selected['month_count']}`",
        f"- Worst month: `{selected['worst_month_pct']:.6f}%`",
        f"- Avg account leverage: `{selected['avg_account_leverage']:.6f}`",
        f"- Max account leverage: `{selected['max_account_leverage']:.6f}`",
        f"- V139 gate passed: `{selected['v139_indicator_leverage_passed']}`",
        f"- Status: `{payload['decision']['status']}`",
        "",
        "## Selected Leverage Policy",
        "",
        json.dumps(payload["config"]["indicator_account_leverage"], indent=2),
        "",
        "## Highest Indicator Sources",
        "",
        indicator_source_summary.to_csv(index=False).strip(),
        "",
        "## Indicator Keys",
        "",
        indicator_key_summary.to_csv(index=False).strip(),
        "",
        "## Selected Account Path By Indicator",
        "",
        leverage_by_key.to_csv(index=False).strip(),
        "",
        "## Monthly Account Return",
        "",
        monthly.to_csv(index=False).strip(),
        "",
        "## Fixed Leverage Comparison",
        "",
        fixed_leverage.to_csv(index=False).strip(),
        "",
        "## Top Indicator Leverage Scan",
        "",
        scan[top_scan_cols].head(20).to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V139 investigates V138 indicators before applying account-level leverage. The strongest total-profit source is v122_drought, but leverage on that source worsened monthly and drawdown risk in the scan, so the selected policy does not promote it. The selected policy promotes only the high-confidence rescue bucket and v123_threshold. It does not filter trades, add daily caps, or use day-end ranking. Leverage rows are account-return approximations, not exchange liquidation guarantees. This is a research candidate, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v138_payload = json.loads(V138_SUMMARY.read_text(encoding="utf-8"))
    trades, rescue = _load_v138_frames()
    enriched = _enrich_indicator_columns(trades, rescue)
    indicator_source_summary = _indicator_summary(enriched, "indicator_source")
    indicator_key_summary = _indicator_summary(enriched, "indicator_key")
    selected_path = _apply_indicator_leverage(
        enriched,
        leverage_map=INDICATOR_ACCOUNT_LEVERAGE,
        default_leverage=DEFAULT_ACCOUNT_LEVERAGE,
    )
    selected = _summarize_account_path("v139_indicator_leverage_rescue_high_5x_v123_1p5x", selected_path)
    v138_1x_path = _apply_indicator_leverage(enriched, leverage_map={}, default_leverage=1.0)
    v138_1x = _summarize_account_path("v138_1x_account_overlay", v138_1x_path)
    selected["vs_v138_1x_account_return_rate"] = (
        float(selected["total_account_return_pct"] / v138_1x["total_account_return_pct"])
        if float(v138_1x["total_account_return_pct"]) > 0.0
        else 0.0
    )
    selected["v139_indicator_leverage_passed"] = _passes_v139_gate(
        selected,
        v138_total_account_return_pct=float(v138_1x["total_account_return_pct"]),
    )
    status = (
        "indicator_leverage_candidate_found"
        if bool(selected["v139_indicator_leverage_passed"])
        else "indicator_leverage_candidate_not_found"
    )
    fixed_leverage = _fixed_leverage_comparison(enriched)
    scan = _scan_indicator_leverage(enriched)
    payload = {
        "version": "v139_btcusdc_indicator_leverage",
        "comparison": {
            "v138_total_net_pnl_bps": float(v138_payload["selected"]["total_net_pnl_bps"]),
            "v138_account_return_pct": float(v138_1x["total_account_return_pct"]),
            "v138_account_max_drawdown_pct": float(v138_1x["max_drawdown_pct"]),
            "v138_positive_months": int(v138_1x["positive_months"]),
            "v138_worst_month_pct": float(v138_1x["worst_month_pct"]),
        },
        "decision": {
            "status": status,
            "risk_gate": {
                "max_selected_drawdown_pct": MAX_SELECTED_DRAWDOWN_PCT,
                "required_positive_months": REQUIRED_POSITIVE_MONTHS,
            },
        },
        "config": _strategy_config(),
        "selected": selected,
        "outputs": {
            "summary_json": str(OUT_DIR / "v139_indicator_leverage_summary.json"),
            "enriched_trades": str(OUT_DIR / "v139_enriched_indicator_trades.csv"),
            "selected_account_path": str(OUT_DIR / "v139_selected_account_path.csv"),
            "indicator_source_summary": str(OUT_DIR / "v139_indicator_source_summary.csv"),
            "indicator_key_summary": str(OUT_DIR / "v139_indicator_key_summary.csv"),
            "fixed_leverage_comparison": str(OUT_DIR / "v139_fixed_leverage_comparison.csv"),
            "indicator_leverage_scan": str(OUT_DIR / "v139_indicator_leverage_scan.csv"),
            "report": str(REPORT_PATH),
        },
    }
    enriched.to_csv(OUT_DIR / "v139_enriched_indicator_trades.csv", index=False)
    selected_path.to_csv(OUT_DIR / "v139_selected_account_path.csv", index=False)
    indicator_source_summary.to_csv(OUT_DIR / "v139_indicator_source_summary.csv", index=False)
    indicator_key_summary.to_csv(OUT_DIR / "v139_indicator_key_summary.csv", index=False)
    fixed_leverage.to_csv(OUT_DIR / "v139_fixed_leverage_comparison.csv", index=False)
    scan.to_csv(OUT_DIR / "v139_indicator_leverage_scan.csv", index=False)
    (OUT_DIR / "v139_indicator_leverage_summary.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    _write_report(payload, indicator_source_summary, indicator_key_summary, selected_path, fixed_leverage, scan)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
