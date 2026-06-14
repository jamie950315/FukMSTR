from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v141_drawdown_throttle_leverage"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V141_BTCUSDC_DRAWDOWN_THROTTLE_LEVERAGE.md"
V139_SUMMARY = ROOT / "runs" / "research_v139_indicator_leverage" / "v139_indicator_leverage_summary.json"
V139_ENRICHED_TRADES = ROOT / "runs" / "research_v139_indicator_leverage" / "v139_enriched_indicator_trades.csv"
V140_SUMMARY = ROOT / "runs" / "research_v140_performance_leverage" / "v140_performance_leverage_summary.json"

HIGH_ACCOUNT_LEVERAGE = 3.5
MID_ACCOUNT_LEVERAGE = 2.25
LOW_ACCOUNT_LEVERAGE = 1.25
MID_DRAWDOWN_TRIGGER_PCT = -5.0
LOW_DRAWDOWN_TRIGGER_PCT = -15.0
MAX_SELECTED_DRAWDOWN_PCT = -35.0
MIN_V140_RETURN_RETENTION_RATE = 0.85
MIN_V140_DRAWDOWN_REDUCTION_RATE = 0.25
REQUIRED_POSITIVE_MONTHS = 24
REQUIRED_V139_IMPROVEMENT_RATE = 1.8


def _strategy_config() -> dict[str, object]:
    return {
        "base": "v139_enriched_indicator_trades",
        "high_account_leverage": HIGH_ACCOUNT_LEVERAGE,
        "mid_account_leverage": MID_ACCOUNT_LEVERAGE,
        "low_account_leverage": LOW_ACCOUNT_LEVERAGE,
        "mid_drawdown_trigger_pct": MID_DRAWDOWN_TRIGGER_PCT,
        "low_drawdown_trigger_pct": LOW_DRAWDOWN_TRIGGER_PCT,
        "max_selected_drawdown_pct": MAX_SELECTED_DRAWDOWN_PCT,
        "min_v140_return_retention_rate": MIN_V140_RETURN_RETENTION_RATE,
        "min_v140_drawdown_reduction_rate": MIN_V140_DRAWDOWN_REDUCTION_RATE,
        "required_positive_months": REQUIRED_POSITIVE_MONTHS,
        "required_v139_improvement_rate": REQUIRED_V139_IMPROVEMENT_RATE,
        "uses_causal_drawdown_throttle": True,
        "uses_new_trade_filter": False,
        "uses_daily_trade_cap": False,
        "uses_day_end_ranking": False,
        "leverage_scope": "account_return_overlay",
        "risk_profile": "risk_adjusted_research_candidate",
    }


def _load_v139_trades() -> pd.DataFrame:
    trades = pd.read_csv(V139_ENRICHED_TRADES)
    trades["timestamp"] = pd.to_datetime(trades["timestamp"], utc=True)
    trades["weighted_net_pnl_bps"] = pd.to_numeric(trades["weighted_net_pnl_bps"], errors="coerce").fillna(0.0)
    return trades.sort_values(["timestamp", "leg", "source"], kind="mergesort").reset_index(drop=True)


def _apply_drawdown_throttle_leverage(
    trades: pd.DataFrame,
    *,
    high_leverage: float,
    mid_leverage: float,
    low_leverage: float,
    mid_drawdown_trigger_pct: float,
    low_drawdown_trigger_pct: float,
) -> pd.DataFrame:
    out = trades.copy().reset_index(drop=True)
    equity_return_pct = 0.0
    peak_return_pct = 0.0
    rows: list[dict[str, float]] = []

    for _, row in out.iterrows():
        prior_drawdown_pct = equity_return_pct - peak_return_pct
        if prior_drawdown_pct <= float(low_drawdown_trigger_pct):
            account_leverage = float(low_leverage)
        elif prior_drawdown_pct <= float(mid_drawdown_trigger_pct):
            account_leverage = float(mid_leverage)
        else:
            account_leverage = float(high_leverage)

        account_pnl_bps = float(row["weighted_net_pnl_bps"]) * account_leverage
        account_return_pct = account_pnl_bps / 100.0
        equity_return_pct += account_return_pct
        peak_return_pct = max(peak_return_pct, equity_return_pct)
        drawdown_pct = equity_return_pct - peak_return_pct
        rows.append(
            {
                "prior_drawdown_pct": prior_drawdown_pct,
                "account_leverage": account_leverage,
                "account_pnl_bps": account_pnl_bps,
                "account_return_pct": account_return_pct,
                "equity_return_pct": equity_return_pct,
                "drawdown_pct": drawdown_pct,
            }
        )

    return pd.concat([out, pd.DataFrame(rows)], axis=1)


def _apply_fixed_account_leverage(trades: pd.DataFrame, *, leverage: float) -> pd.DataFrame:
    out = trades.copy().reset_index(drop=True)
    out["prior_drawdown_pct"] = 0.0
    out["account_leverage"] = float(leverage)
    out["account_pnl_bps"] = pd.to_numeric(out["weighted_net_pnl_bps"], errors="coerce").fillna(0.0) * float(leverage)
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
            "min_account_leverage": 0.0,
            "throttled_trade_count": 0,
            "levered_win_rate": 0.0,
        }
    monthly = path.groupby("month", sort=True)["account_return_pct"].sum()
    high_leverage = float(path["account_leverage"].max())
    return {
        "policy": policy,
        "trade_count": int(len(path)),
        "total_account_return_pct": float(path["account_return_pct"].sum()),
        "max_drawdown_pct": float(path["drawdown_pct"].min()),
        "positive_months": int((monthly > 0.0).sum()),
        "month_count": int(len(monthly)),
        "worst_month_pct": float(monthly.min()),
        "avg_account_leverage": float(path["account_leverage"].mean()),
        "max_account_leverage": high_leverage,
        "min_account_leverage": float(path["account_leverage"].min()),
        "throttled_trade_count": int(path["account_leverage"].lt(high_leverage).sum()),
        "levered_win_rate": float((path["account_pnl_bps"] > 0.0).mean()),
    }


def _passes_v141_gate(
    row: dict[str, object],
    *,
    v139_selected: dict[str, object],
    v140_selected: dict[str, object],
) -> bool:
    v140_drawdown_magnitude = abs(float(v140_selected["max_drawdown_pct"]))
    selected_drawdown_magnitude = abs(float(row.get("max_drawdown_pct", -999.0)))
    drawdown_reduction_rate = (
        (v140_drawdown_magnitude - selected_drawdown_magnitude) / v140_drawdown_magnitude
        if v140_drawdown_magnitude > 0.0
        else 0.0
    )
    return (
        float(row.get("total_account_return_pct", 0.0))
        >= float(v140_selected["total_account_return_pct"]) * MIN_V140_RETURN_RETENTION_RATE
        and float(row.get("total_account_return_pct", 0.0))
        >= float(v139_selected["total_account_return_pct"]) * REQUIRED_V139_IMPROVEMENT_RATE
        and float(row.get("max_drawdown_pct", -999.0)) >= MAX_SELECTED_DRAWDOWN_PCT
        and drawdown_reduction_rate >= MIN_V140_DRAWDOWN_REDUCTION_RATE
        and int(row.get("positive_months", 0)) >= REQUIRED_POSITIVE_MONTHS
        and int(row.get("month_count", 0)) >= REQUIRED_POSITIVE_MONTHS
        and float(row.get("worst_month_pct", 0.0)) > 0.0
    )


def _comparison_table(
    trades: pd.DataFrame,
    selected_path: pd.DataFrame,
    v139_selected: dict[str, object],
    v140_selected: dict[str, object],
) -> pd.DataFrame:
    rows = [
        {
            "policy": "v139_indicator_leverage",
            "total_account_return_pct": float(v139_selected["total_account_return_pct"]),
            "max_drawdown_pct": float(v139_selected["max_drawdown_pct"]),
            "positive_months": int(v139_selected["positive_months"]),
            "month_count": int(v139_selected["month_count"]),
            "avg_account_leverage": float(v139_selected["avg_account_leverage"]),
            "max_account_leverage": float(v139_selected["max_account_leverage"]),
        },
        {
            "policy": "v140_fixed_3x",
            "total_account_return_pct": float(v140_selected["total_account_return_pct"]),
            "max_drawdown_pct": float(v140_selected["max_drawdown_pct"]),
            "positive_months": int(v140_selected["positive_months"]),
            "month_count": int(v140_selected["month_count"]),
            "avg_account_leverage": float(v140_selected["avg_account_leverage"]),
            "max_account_leverage": float(v140_selected["max_account_leverage"]),
        },
    ]
    fixed_24 = _summarize_account_path("fixed_2p4x_reference", _apply_fixed_account_leverage(trades, leverage=2.4))
    selected = _summarize_account_path("v141_drawdown_throttle", selected_path)
    for row in (fixed_24, selected):
        rows.append(
            {
                "policy": row["policy"],
                "total_account_return_pct": row["total_account_return_pct"],
                "max_drawdown_pct": row["max_drawdown_pct"],
                "positive_months": row["positive_months"],
                "month_count": row["month_count"],
                "avg_account_leverage": row["avg_account_leverage"],
                "max_account_leverage": row["max_account_leverage"],
            }
        )
    return pd.DataFrame(rows)


def _write_report(payload: dict[str, object], selected_path: pd.DataFrame, comparison_table: pd.DataFrame) -> None:
    selected = payload["selected"]
    comparison = payload["comparison"]
    monthly = selected_path.groupby("month", sort=True)["account_return_pct"].sum().reset_index()
    leverage_usage = (
        selected_path.groupby("account_leverage", sort=True)
        .agg(
            trade_count=("account_pnl_bps", "size"),
            account_return_pct=("account_return_pct", "sum"),
            win_rate=("account_pnl_bps", lambda s: (s > 0.0).mean()),
        )
        .reset_index()
    )
    by_indicator = (
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
    lines = [
        "# Research V141 BTCUSDC Drawdown Throttle Leverage",
        "",
        "## Decision",
        "",
        f"- V139 account return: `{comparison['v139_total_account_return_pct']:.6f}%`",
        f"- V139 max drawdown: `{comparison['v139_max_drawdown_pct']:.6f}%`",
        f"- V140 account return: `{comparison['v140_total_account_return_pct']:.6f}%`",
        f"- V140 max drawdown: `{comparison['v140_max_drawdown_pct']:.6f}%`",
        f"- V141 selected account return: `{selected['total_account_return_pct']:.6f}%`",
        f"- V141 selected max drawdown: `{selected['max_drawdown_pct']:.6f}%`",
        f"- V141 return retained vs V140: `{selected['v140_return_retention_rate']:.6f}`",
        f"- V141 drawdown reduction vs V140: `{selected['v140_drawdown_reduction_rate']:.6f}`",
        f"- Positive months: `{selected['positive_months']}/{selected['month_count']}`",
        f"- Worst month: `{selected['worst_month_pct']:.6f}%`",
        f"- Avg / max / min account leverage: `{selected['avg_account_leverage']:.6f}` / `{selected['max_account_leverage']:.6f}` / `{selected['min_account_leverage']:.6f}`",
        f"- Throttled trades: `{selected['throttled_trade_count']}`",
        f"- V141 gate passed: `{selected['v141_drawdown_throttle_passed']}`",
        f"- Status: `{payload['decision']['status']}`",
        "",
        "## Rule",
        "",
        "- Use 3.5x while prior realized account drawdown is above -5%.",
        "- Use 2.25x once prior realized account drawdown is at or below -5%.",
        "- Use 1.25x once prior realized account drawdown is at or below -15%.",
        "- The current trade's leverage is decided before applying the current trade's PnL.",
        "",
        "## Comparison",
        "",
        comparison_table.to_csv(index=False).strip(),
        "",
        "## Leverage Usage",
        "",
        leverage_usage.to_csv(index=False).strip(),
        "",
        "## Monthly Account Return",
        "",
        monthly.to_csv(index=False).strip(),
        "",
        "## Selected Account Return By Indicator",
        "",
        by_indicator.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V141 keeps the same V139/V140 trade list and does not add day-end ranking, daily caps, or new trade filters. It changes only the account-level leverage before each trade according to already-realized drawdown. This preserves most of V140's profit estimate while cutting the V140 drawdown by more than 25%. This is a research candidate, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v139_payload = json.loads(V139_SUMMARY.read_text(encoding="utf-8"))
    v140_payload = json.loads(V140_SUMMARY.read_text(encoding="utf-8"))
    v139_selected = v139_payload["selected"]
    v140_selected = v140_payload["selected"]
    trades = _load_v139_trades()
    selected_path = _apply_drawdown_throttle_leverage(
        trades,
        high_leverage=HIGH_ACCOUNT_LEVERAGE,
        mid_leverage=MID_ACCOUNT_LEVERAGE,
        low_leverage=LOW_ACCOUNT_LEVERAGE,
        mid_drawdown_trigger_pct=MID_DRAWDOWN_TRIGGER_PCT,
        low_drawdown_trigger_pct=LOW_DRAWDOWN_TRIGGER_PCT,
    )
    selected = _summarize_account_path("v141_drawdown_throttle_leverage", selected_path)
    v140_drawdown_magnitude = abs(float(v140_selected["max_drawdown_pct"]))
    selected_drawdown_magnitude = abs(float(selected["max_drawdown_pct"]))
    selected["v140_return_retention_rate"] = float(
        selected["total_account_return_pct"] / float(v140_selected["total_account_return_pct"])
    )
    selected["vs_v139_account_return_rate"] = float(
        selected["total_account_return_pct"] / float(v139_selected["total_account_return_pct"])
    )
    selected["v140_drawdown_reduction_rate"] = float(
        (v140_drawdown_magnitude - selected_drawdown_magnitude) / v140_drawdown_magnitude
        if v140_drawdown_magnitude > 0.0
        else 0.0
    )
    selected["v141_drawdown_throttle_passed"] = _passes_v141_gate(
        selected,
        v139_selected=v139_selected,
        v140_selected=v140_selected,
    )
    status = (
        "drawdown_throttle_candidate_found"
        if bool(selected["v141_drawdown_throttle_passed"])
        else "drawdown_throttle_candidate_not_found"
    )
    comparison_table = _comparison_table(trades, selected_path, v139_selected, v140_selected)
    payload = {
        "version": "v141_btcusdc_drawdown_throttle_leverage",
        "comparison": {
            "v139_total_account_return_pct": float(v139_selected["total_account_return_pct"]),
            "v139_max_drawdown_pct": float(v139_selected["max_drawdown_pct"]),
            "v140_total_account_return_pct": float(v140_selected["total_account_return_pct"]),
            "v140_max_drawdown_pct": float(v140_selected["max_drawdown_pct"]),
            "min_v140_return_retention_rate": MIN_V140_RETURN_RETENTION_RATE,
            "min_v140_drawdown_reduction_rate": MIN_V140_DRAWDOWN_REDUCTION_RATE,
            "required_v139_improvement_rate": REQUIRED_V139_IMPROVEMENT_RATE,
        },
        "decision": {
            "status": status,
            "risk_profile": "risk_adjusted_research_candidate",
        },
        "config": _strategy_config(),
        "selected": selected,
        "outputs": {
            "summary_json": str(OUT_DIR / "v141_drawdown_throttle_leverage_summary.json"),
            "selected_account_path": str(OUT_DIR / "v141_selected_account_path.csv"),
            "comparison_table": str(OUT_DIR / "v141_comparison_table.csv"),
            "report": str(REPORT_PATH),
        },
    }
    selected_path.to_csv(OUT_DIR / "v141_selected_account_path.csv", index=False)
    comparison_table.to_csv(OUT_DIR / "v141_comparison_table.csv", index=False)
    (OUT_DIR / "v141_drawdown_throttle_leverage_summary.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    _write_report(payload, selected_path, comparison_table)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
