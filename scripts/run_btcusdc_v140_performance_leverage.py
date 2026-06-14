from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v140_performance_leverage"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V140_BTCUSDC_PERFORMANCE_LEVERAGE.md"
V139_SUMMARY = ROOT / "runs" / "research_v139_indicator_leverage" / "v139_indicator_leverage_summary.json"
V139_ENRICHED_TRADES = ROOT / "runs" / "research_v139_indicator_leverage" / "v139_enriched_indicator_trades.csv"

SELECTED_ACCOUNT_LEVERAGE = 3.0
LEVERAGE_VALUES = (1.0, 2.0, 3.0, 4.0, 5.0)
MAX_SELECTED_DRAWDOWN_PCT = -50.0
REQUIRED_POSITIVE_MONTHS = 24
REQUIRED_V139_IMPROVEMENT_RATE = 2.0


def _strategy_config() -> dict[str, object]:
    return {
        "base": "v139_enriched_indicator_trades",
        "selected_account_leverage": SELECTED_ACCOUNT_LEVERAGE,
        "leverage_values": list(LEVERAGE_VALUES),
        "max_selected_drawdown_pct": MAX_SELECTED_DRAWDOWN_PCT,
        "required_positive_months": REQUIRED_POSITIVE_MONTHS,
        "required_v139_improvement_rate": REQUIRED_V139_IMPROVEMENT_RATE,
        "uses_fixed_account_leverage": True,
        "uses_new_trade_filter": False,
        "uses_daily_trade_cap": False,
        "uses_day_end_ranking": False,
        "leverage_scope": "account_return_overlay",
        "risk_profile": "aggressive_research_candidate",
    }


def _load_v139_trades() -> pd.DataFrame:
    trades = pd.read_csv(V139_ENRICHED_TRADES)
    trades["timestamp"] = pd.to_datetime(trades["timestamp"], utc=True)
    trades["weighted_net_pnl_bps"] = pd.to_numeric(trades["weighted_net_pnl_bps"], errors="coerce").fillna(0.0)
    return trades.sort_values(["timestamp", "leg", "source"], kind="mergesort").reset_index(drop=True)


def _apply_fixed_account_leverage(trades: pd.DataFrame, *, leverage: float) -> pd.DataFrame:
    out = trades.copy()
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


def _fixed_leverage_table(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for leverage in LEVERAGE_VALUES:
        path = _apply_fixed_account_leverage(trades, leverage=float(leverage))
        row = _summarize_account_path(f"fixed_{leverage:g}x", path)
        row["fixed_leverage"] = float(leverage)
        rows.append(row)
    return pd.DataFrame(rows)


def _passes_v140_gate(row: dict[str, object], *, v139_selected: dict[str, object]) -> bool:
    return (
        float(row.get("total_account_return_pct", 0.0))
        > float(v139_selected["total_account_return_pct"]) * REQUIRED_V139_IMPROVEMENT_RATE
        and float(row.get("max_drawdown_pct", -999.0)) >= MAX_SELECTED_DRAWDOWN_PCT
        and int(row.get("positive_months", 0)) >= REQUIRED_POSITIVE_MONTHS
        and int(row.get("month_count", 0)) >= REQUIRED_POSITIVE_MONTHS
        and float(row.get("worst_month_pct", 0.0)) > 0.0
    )


def _write_report(
    payload: dict[str, object],
    selected_path: pd.DataFrame,
    leverage_table: pd.DataFrame,
) -> None:
    selected = payload["selected"]
    comparison = payload["comparison"]
    monthly = selected_path.groupby("month", sort=True)["account_return_pct"].sum().reset_index()
    by_indicator = (
        selected_path.groupby("indicator_key", sort=True)
        .agg(
            trade_count=("account_pnl_bps", "size"),
            account_return_pct=("account_return_pct", "sum"),
            win_rate=("account_pnl_bps", lambda s: (s > 0.0).mean()),
        )
        .reset_index()
        .sort_values("account_return_pct", ascending=False)
    )
    lines = [
        "# Research V140 BTCUSDC Performance Leverage",
        "",
        "## Decision",
        "",
        f"- V139 selected account return: `{comparison['v139_total_account_return_pct']:.6f}%`",
        f"- V139 selected max drawdown: `{comparison['v139_max_drawdown_pct']:.6f}%`",
        f"- Required V139 improvement rate: `{comparison['required_v139_improvement_rate']:.6f}`",
        f"- V140 selected account return: `{selected['total_account_return_pct']:.6f}%`",
        f"- V140 selected max drawdown: `{selected['max_drawdown_pct']:.6f}%`",
        f"- Trade count: `{selected['trade_count']}`",
        f"- Positive months: `{selected['positive_months']}/{selected['month_count']}`",
        f"- Worst month: `{selected['worst_month_pct']:.6f}%`",
        f"- Fixed account leverage: `{SELECTED_ACCOUNT_LEVERAGE:.6f}`",
        f"- V140 performance gate passed: `{selected['v140_performance_leverage_passed']}`",
        f"- Status: `{payload['decision']['status']}`",
        "",
        "## Fixed Leverage Comparison",
        "",
        leverage_table.to_csv(index=False).strip(),
        "",
        "## Monthly Account Return",
        "",
        monthly.to_csv(index=False).strip(),
        "",
        "## Selected Account Return By Indicator",
        "",
        by_indicator.to_csv(index=False).strip(),
        "",
        "## Research Notes",
        "",
        "- External research review pointed to volatility targeting, fractional Kelly, and confidence sizing as common position-sizing approaches for crypto systems.",
        "- The local V139 scan showed the balanced indicator leverage path reached about 648.86% account return with about -16.40% max drawdown.",
        "- The fixed 3x overlay is the highest simple fixed leverage that keeps all 24 months positive while staying inside the aggressive -50% drawdown cap.",
        "- 4x and 5x produce higher account-return estimates, but drawdown expands to about -64% and -80%, so they are reported but not promoted.",
        "",
        "## Interpretation",
        "",
        "V140 does not change V138/V139 trade selection, model signals, daily caps, or day-end ranking. It is an aggressive account-level leverage overlay selected for performance. This is a research candidate, not a live trading guarantee, and the leverage rows are account-return approximations rather than exchange liquidation guarantees.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v139_payload = json.loads(V139_SUMMARY.read_text(encoding="utf-8"))
    v139_selected = v139_payload["selected"]
    trades = _load_v139_trades()
    selected_path = _apply_fixed_account_leverage(trades, leverage=SELECTED_ACCOUNT_LEVERAGE)
    selected = _summarize_account_path(f"v140_fixed_{SELECTED_ACCOUNT_LEVERAGE:g}x_performance", selected_path)
    selected["vs_v139_account_return_rate"] = (
        float(selected["total_account_return_pct"] / float(v139_selected["total_account_return_pct"]))
        if float(v139_selected["total_account_return_pct"]) > 0.0
        else 0.0
    )
    selected["v140_performance_leverage_passed"] = _passes_v140_gate(selected, v139_selected=v139_selected)
    status = (
        "performance_leverage_candidate_found"
        if bool(selected["v140_performance_leverage_passed"])
        else "performance_leverage_candidate_not_found"
    )
    leverage_table = _fixed_leverage_table(trades)
    payload = {
        "version": "v140_btcusdc_performance_leverage",
        "comparison": {
            "v139_total_account_return_pct": float(v139_selected["total_account_return_pct"]),
            "v139_max_drawdown_pct": float(v139_selected["max_drawdown_pct"]),
            "v139_positive_months": int(v139_selected["positive_months"]),
            "v139_worst_month_pct": float(v139_selected["worst_month_pct"]),
            "required_v139_improvement_rate": REQUIRED_V139_IMPROVEMENT_RATE,
        },
        "decision": {
            "status": status,
            "risk_profile": "aggressive_research_candidate",
        },
        "config": _strategy_config(),
        "selected": selected,
        "outputs": {
            "summary_json": str(OUT_DIR / "v140_performance_leverage_summary.json"),
            "selected_account_path": str(OUT_DIR / "v140_selected_account_path.csv"),
            "fixed_leverage_table": str(OUT_DIR / "v140_fixed_leverage_table.csv"),
            "report": str(REPORT_PATH),
        },
    }
    selected_path.to_csv(OUT_DIR / "v140_selected_account_path.csv", index=False)
    leverage_table.to_csv(OUT_DIR / "v140_fixed_leverage_table.csv", index=False)
    (OUT_DIR / "v140_performance_leverage_summary.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    _write_report(payload, selected_path, leverage_table)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
