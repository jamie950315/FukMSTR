from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v142_high_confidence_rescue_5x"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V142_BTCUSDC_HIGH_CONFIDENCE_RESCUE_5X.md"
V139_ENRICHED_TRADES = ROOT / "runs" / "research_v139_indicator_leverage" / "v139_enriched_indicator_trades.csv"
V140_SUMMARY = ROOT / "runs" / "research_v140_performance_leverage" / "v140_performance_leverage_summary.json"
V141_SUMMARY = ROOT / "runs" / "research_v141_drawdown_throttle_leverage" / "v141_drawdown_throttle_leverage_summary.json"

HIGH_CONFIDENCE_RESCUE_LEVERAGE = 5.0
HIGH_CONFIDENCE_PROBABILITY_FLOOR = 0.66
HIGH_ACCOUNT_LEVERAGE = 3.5
MID_ACCOUNT_LEVERAGE = 2.25
LOW_ACCOUNT_LEVERAGE = 1.25
MID_DRAWDOWN_TRIGGER_PCT = -5.0
LOW_DRAWDOWN_TRIGGER_PCT = -15.0
REQUIRED_POSITIVE_MONTHS = 24
MIN_V141_IMPROVEMENT_RATE = 1.005
MAX_V141_DRAWDOWN_DEGRADATION_PCT = 0.0
FLOAT_TOLERANCE_PCT = 1e-9


def _strategy_config() -> dict[str, object]:
    return {
        "base": "v139_enriched_indicator_trades",
        "high_confidence_rescue_leverage": HIGH_CONFIDENCE_RESCUE_LEVERAGE,
        "high_confidence_probability_floor": HIGH_CONFIDENCE_PROBABILITY_FLOOR,
        "high_account_leverage": HIGH_ACCOUNT_LEVERAGE,
        "mid_account_leverage": MID_ACCOUNT_LEVERAGE,
        "low_account_leverage": LOW_ACCOUNT_LEVERAGE,
        "mid_drawdown_trigger_pct": MID_DRAWDOWN_TRIGGER_PCT,
        "low_drawdown_trigger_pct": LOW_DRAWDOWN_TRIGGER_PCT,
        "required_positive_months": REQUIRED_POSITIVE_MONTHS,
        "min_v141_improvement_rate": MIN_V141_IMPROVEMENT_RATE,
        "max_v141_drawdown_degradation_pct": MAX_V141_DRAWDOWN_DEGRADATION_PCT,
        "float_tolerance_pct": FLOAT_TOLERANCE_PCT,
        "uses_high_confidence_rescue_5x": True,
        "uses_causal_drawdown_throttle": True,
        "uses_new_trade_filter": False,
        "uses_daily_trade_cap": False,
        "uses_day_end_ranking": False,
        "leverage_scope": "account_return_overlay",
        "risk_profile": "high_confidence_rescue_overlay_candidate",
    }


def _load_v139_trades() -> pd.DataFrame:
    trades = pd.read_csv(V139_ENRICHED_TRADES)
    trades["timestamp"] = pd.to_datetime(trades["timestamp"], utc=True)
    trades["weighted_net_pnl_bps"] = pd.to_numeric(trades["weighted_net_pnl_bps"], errors="coerce").fillna(0.0)
    trades["direction_probability"] = pd.to_numeric(trades.get("direction_probability"), errors="coerce")
    return trades.sort_values(["timestamp", "leg", "source"], kind="mergesort").reset_index(drop=True)


def _is_high_confidence_rescue(row: pd.Series, *, probability_floor: float) -> bool:
    return (
        str(row.get("leg", "")) == "rescue"
        and pd.notna(row.get("direction_probability"))
        and float(row.get("direction_probability")) >= float(probability_floor)
    )


def _apply_high_confidence_rescue_leverage(
    trades: pd.DataFrame,
    *,
    high_confidence_leverage: float,
    high_confidence_probability_floor: float,
    high_leverage: float,
    mid_leverage: float,
    low_leverage: float,
    mid_drawdown_trigger_pct: float,
    low_drawdown_trigger_pct: float,
) -> pd.DataFrame:
    out = trades.copy().reset_index(drop=True)
    if "direction_probability" not in out.columns:
        out["direction_probability"] = pd.NA
    equity_return_pct = 0.0
    peak_return_pct = 0.0
    rows: list[dict[str, float | bool]] = []

    for _, row in out.iterrows():
        prior_drawdown_pct = equity_return_pct - peak_return_pct
        high_confidence_eligible = _is_high_confidence_rescue(
            row,
            probability_floor=high_confidence_probability_floor,
        )
        if prior_drawdown_pct <= float(low_drawdown_trigger_pct):
            account_leverage = float(low_leverage)
            uses_high_confidence_5x = False
        elif prior_drawdown_pct <= float(mid_drawdown_trigger_pct):
            account_leverage = float(mid_leverage)
            uses_high_confidence_5x = False
        elif high_confidence_eligible:
            account_leverage = float(high_confidence_leverage)
            uses_high_confidence_5x = True
        else:
            account_leverage = float(high_leverage)
            uses_high_confidence_5x = False

        account_pnl_bps = float(row["weighted_net_pnl_bps"]) * account_leverage
        account_return_pct = account_pnl_bps / 100.0
        equity_return_pct += account_return_pct
        peak_return_pct = max(peak_return_pct, equity_return_pct)
        drawdown_pct = equity_return_pct - peak_return_pct
        rows.append(
            {
                "prior_drawdown_pct": prior_drawdown_pct,
                "account_leverage": account_leverage,
                "high_confidence_rescue_5x": uses_high_confidence_5x,
                "account_pnl_bps": account_pnl_bps,
                "account_return_pct": account_return_pct,
                "equity_return_pct": equity_return_pct,
                "drawdown_pct": drawdown_pct,
            }
        )

    return pd.concat([out, pd.DataFrame(rows)], axis=1)


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
            "high_confidence_5x_trade_count": 0,
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
        "min_account_leverage": float(path["account_leverage"].min()),
        "high_confidence_5x_trade_count": int(path["high_confidence_rescue_5x"].sum()),
        "levered_win_rate": float((path["account_pnl_bps"] > 0.0).mean()),
    }


def _passes_v142_gate(row: dict[str, object], *, v141_selected: dict[str, object]) -> bool:
    return (
        float(row.get("total_account_return_pct", 0.0))
        >= float(v141_selected["total_account_return_pct"]) * MIN_V141_IMPROVEMENT_RATE
        and float(row.get("max_drawdown_pct", -999.0))
        >= float(v141_selected["max_drawdown_pct"]) - MAX_V141_DRAWDOWN_DEGRADATION_PCT - FLOAT_TOLERANCE_PCT
        and int(row.get("positive_months", 0)) >= REQUIRED_POSITIVE_MONTHS
        and int(row.get("month_count", 0)) >= REQUIRED_POSITIVE_MONTHS
        and float(row.get("worst_month_pct", 0.0)) > 0.0
        and int(row.get("high_confidence_5x_trade_count", 0)) > 0
    )


def _write_report(payload: dict[str, object], selected_path: pd.DataFrame, comparison_table: pd.DataFrame) -> None:
    selected = payload["selected"]
    comparison = payload["comparison"]
    monthly = selected_path.groupby("month", sort=True)["account_return_pct"].sum().reset_index()
    leverage_usage = (
        selected_path.groupby(["account_leverage", "high_confidence_rescue_5x"], sort=True)
        .agg(
            trade_count=("account_pnl_bps", "size"),
            account_return_pct=("account_return_pct", "sum"),
            win_rate=("account_pnl_bps", lambda s: (s > 0.0).mean()),
        )
        .reset_index()
    )
    high_confidence_rows = selected_path.loc[selected_path["high_confidence_rescue_5x"]].copy()
    high_confidence_table = (
        high_confidence_rows[
            [
                "timestamp",
                "indicator_key",
                "direction_probability",
                "weighted_net_pnl_bps",
                "account_leverage",
                "account_return_pct",
                "drawdown_pct",
            ]
        ]
        if not high_confidence_rows.empty
        else pd.DataFrame(
            columns=[
                "timestamp",
                "indicator_key",
                "direction_probability",
                "weighted_net_pnl_bps",
                "account_leverage",
                "account_return_pct",
                "drawdown_pct",
            ]
        )
    )
    lines = [
        "# Research V142 BTCUSDC High Confidence Rescue 5x",
        "",
        "## Decision",
        "",
        f"- V140 account return: `{comparison['v140_total_account_return_pct']:.6f}%`",
        f"- V140 max drawdown: `{comparison['v140_max_drawdown_pct']:.6f}%`",
        f"- V141 account return: `{comparison['v141_total_account_return_pct']:.6f}%`",
        f"- V141 max drawdown: `{comparison['v141_max_drawdown_pct']:.6f}%`",
        f"- V142 selected account return: `{selected['total_account_return_pct']:.6f}%`",
        f"- V142 selected max drawdown: `{selected['max_drawdown_pct']:.6f}%`",
        f"- V142 improvement vs V141: `{selected['vs_v141_account_return_rate']:.6f}`",
        f"- High-confidence 5x trades: `{selected['high_confidence_5x_trade_count']}`",
        f"- Positive months: `{selected['positive_months']}/{selected['month_count']}`",
        f"- Worst month: `{selected['worst_month_pct']:.6f}%`",
        f"- Avg / max / min account leverage: `{selected['avg_account_leverage']:.6f}` / `{selected['max_account_leverage']:.6f}` / `{selected['min_account_leverage']:.6f}`",
        f"- V142 gate passed: `{selected['v142_high_confidence_rescue_5x_passed']}`",
        f"- Status: `{payload['decision']['status']}`",
        "",
        "## Rule",
        "",
        "- Use 5x only for rescue trades with direction_probability >= 0.66 while prior realized account drawdown is above -5%.",
        "- Use 3.5x for normal trades while prior realized account drawdown is above -5%.",
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
        "## High Confidence 5x Trades",
        "",
        high_confidence_table.to_csv(index=False).strip(),
        "",
        "## Monthly Account Return",
        "",
        monthly.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V142 keeps the same V139/V141 trade list and does not add day-end ranking, daily caps, or new trade filters. It only lets the historical high-confidence rescue zone use 5x when the account is not already in drawdown defense. This is a research candidate, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v140_payload = json.loads(V140_SUMMARY.read_text(encoding="utf-8"))
    v141_payload = json.loads(V141_SUMMARY.read_text(encoding="utf-8"))
    v140_selected = v140_payload["selected"]
    v141_selected = v141_payload["selected"]
    trades = _load_v139_trades()
    selected_path = _apply_high_confidence_rescue_leverage(
        trades,
        high_confidence_leverage=HIGH_CONFIDENCE_RESCUE_LEVERAGE,
        high_confidence_probability_floor=HIGH_CONFIDENCE_PROBABILITY_FLOOR,
        high_leverage=HIGH_ACCOUNT_LEVERAGE,
        mid_leverage=MID_ACCOUNT_LEVERAGE,
        low_leverage=LOW_ACCOUNT_LEVERAGE,
        mid_drawdown_trigger_pct=MID_DRAWDOWN_TRIGGER_PCT,
        low_drawdown_trigger_pct=LOW_DRAWDOWN_TRIGGER_PCT,
    )
    selected = _summarize_account_path("v142_high_confidence_rescue_5x", selected_path)
    selected["vs_v141_account_return_rate"] = float(
        selected["total_account_return_pct"] / float(v141_selected["total_account_return_pct"])
    )
    selected["v142_high_confidence_rescue_5x_passed"] = _passes_v142_gate(
        selected,
        v141_selected=v141_selected,
    )
    status = (
        "high_confidence_rescue_5x_candidate_found"
        if bool(selected["v142_high_confidence_rescue_5x_passed"])
        else "high_confidence_rescue_5x_candidate_not_found"
    )
    comparison_table = pd.DataFrame(
        [
            {
                "policy": "v140_fixed_3x",
                "total_account_return_pct": float(v140_selected["total_account_return_pct"]),
                "max_drawdown_pct": float(v140_selected["max_drawdown_pct"]),
                "positive_months": int(v140_selected["positive_months"]),
                "month_count": int(v140_selected["month_count"]),
                "avg_account_leverage": float(v140_selected["avg_account_leverage"]),
                "max_account_leverage": float(v140_selected["max_account_leverage"]),
            },
            {
                "policy": "v141_drawdown_throttle",
                "total_account_return_pct": float(v141_selected["total_account_return_pct"]),
                "max_drawdown_pct": float(v141_selected["max_drawdown_pct"]),
                "positive_months": int(v141_selected["positive_months"]),
                "month_count": int(v141_selected["month_count"]),
                "avg_account_leverage": float(v141_selected["avg_account_leverage"]),
                "max_account_leverage": float(v141_selected["max_account_leverage"]),
            },
            {
                "policy": selected["policy"],
                "total_account_return_pct": selected["total_account_return_pct"],
                "max_drawdown_pct": selected["max_drawdown_pct"],
                "positive_months": selected["positive_months"],
                "month_count": selected["month_count"],
                "avg_account_leverage": selected["avg_account_leverage"],
                "max_account_leverage": selected["max_account_leverage"],
            },
        ]
    )
    payload = {
        "version": "v142_btcusdc_high_confidence_rescue_5x",
        "comparison": {
            "v140_total_account_return_pct": float(v140_selected["total_account_return_pct"]),
            "v140_max_drawdown_pct": float(v140_selected["max_drawdown_pct"]),
            "v141_total_account_return_pct": float(v141_selected["total_account_return_pct"]),
            "v141_max_drawdown_pct": float(v141_selected["max_drawdown_pct"]),
            "min_v141_improvement_rate": MIN_V141_IMPROVEMENT_RATE,
        },
        "decision": {
            "status": status,
            "risk_profile": "high_confidence_rescue_overlay_candidate",
        },
        "config": _strategy_config(),
        "selected": selected,
        "outputs": {
            "summary_json": str(OUT_DIR / "v142_high_confidence_rescue_5x_summary.json"),
            "selected_account_path": str(OUT_DIR / "v142_selected_account_path.csv"),
            "comparison_table": str(OUT_DIR / "v142_comparison_table.csv"),
            "report": str(REPORT_PATH),
        },
    }
    selected_path.to_csv(OUT_DIR / "v142_selected_account_path.csv", index=False)
    comparison_table.to_csv(OUT_DIR / "v142_comparison_table.csv", index=False)
    (OUT_DIR / "v142_high_confidence_rescue_5x_summary.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    _write_report(payload, selected_path, comparison_table)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
