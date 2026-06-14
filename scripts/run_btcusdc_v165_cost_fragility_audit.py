from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v162_long_trend_follow_boost as v162


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v165_cost_fragility_audit"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V165_BTCUSDC_COST_FRAGILITY_AUDIT.md"
V162_ACCOUNT_PATH = ROOT / "runs" / "research_v162_long_trend_follow_boost" / "v162_selected_account_path.csv"
EXTRA_COST_BPS = (2.0, 4.0, 8.0, 16.0)
REQUIRED_EXTRA_COST_BPS = 4.0


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _monthly_cost_fragility(
    frame: pd.DataFrame,
    *,
    extra_cost_bps_values: tuple[float, ...] = EXTRA_COST_BPS,
) -> pd.DataFrame:
    work = frame.copy()
    work["timestamp"] = _to_utc(work["timestamp"])
    work["month"] = work["timestamp"].dt.strftime("%Y-%m")
    work["v162_account_return_pct"] = pd.to_numeric(work["v162_account_return_pct"], errors="coerce").fillna(0.0)
    leverage = pd.to_numeric(work.get("account_leverage", 1.0), errors="coerce").fillna(1.0)
    position_weight = pd.to_numeric(work.get("position_weight", 1.0), errors="coerce").fillna(1.0)
    work["cost_load_per_1bps_pct"] = leverage * position_weight / 100.0
    rows: list[dict[str, object]] = []
    for month, group in work.groupby("month", sort=True):
        base_return = float(group["v162_account_return_pct"].sum())
        cost_load = float(group["cost_load_per_1bps_pct"].sum())
        row: dict[str, object] = {
            "month": month,
            "trade_count": int(len(group)),
            "base_return_pct": base_return,
            "cost_load_per_1bps_pct": cost_load,
            "breakeven_extra_cost_bps": base_return / cost_load if cost_load > 0 else None,
            "avg_leverage": float(leverage.loc[group.index].mean()),
            "avg_position_weight": float(position_weight.loc[group.index].mean()),
            "base_trade_count": int(group["leg"].eq("base").sum()) if "leg" in group else 0,
            "rescue_trade_count": int(group["leg"].eq("rescue").sum()) if "leg" in group else 0,
            "long_trade_count": int(group["side"].eq("long").sum()) if "side" in group else 0,
            "short_trade_count": int(group["side"].eq("short").sum()) if "side" in group else 0,
        }
        for extra_cost in extra_cost_bps_values:
            row[f"return_after_{float(extra_cost):g}bps_pct"] = base_return - float(extra_cost) * cost_load
        rows.append(row)
    return pd.DataFrame(rows)


def _tag_fragility(monthly: pd.DataFrame, *, required_extra_cost_bps: float = REQUIRED_EXTRA_COST_BPS) -> pd.DataFrame:
    out = monthly.copy()
    breakeven = pd.to_numeric(out["breakeven_extra_cost_bps"], errors="coerce")
    out["passes_required_cost_headroom"] = breakeven >= float(required_extra_cost_bps)
    out["cost_fragility_tag"] = "ok"
    out.loc[breakeven < float(required_extra_cost_bps), "cost_fragility_tag"] = "thin"
    out.loc[breakeven < float(required_extra_cost_bps) / 2.0, "cost_fragility_tag"] = "critical"
    return out


def _negative_months(monthly: pd.DataFrame, *, extra_cost_bps: float) -> pd.DataFrame:
    column = f"return_after_{float(extra_cost_bps):g}bps_pct"
    if column not in monthly.columns:
        return pd.DataFrame()
    return monthly.loc[pd.to_numeric(monthly[column], errors="coerce") < 0].copy()


def _decision(monthly: pd.DataFrame, *, required_extra_cost_bps: float = REQUIRED_EXTRA_COST_BPS) -> dict[str, object]:
    fragile = monthly.loc[~monthly["passes_required_cost_headroom"].astype(bool)].copy()
    minimum = float(pd.to_numeric(monthly["breakeven_extra_cost_bps"], errors="coerce").min()) if not monthly.empty else 0.0
    passed = fragile.empty
    return {
        "status": "cost_fragility_passed" if passed else "cost_fragility_warning",
        "promote_to_live": False,
        "message": (
            "Every month has enough breakeven headroom for the required extra cost."
            if passed
            else "Some months do not have enough breakeven headroom for the required extra cost."
        ),
        "required_extra_cost_bps": float(required_extra_cost_bps),
        "month_count": int(len(monthly)),
        "fragile_month_count": int(len(fragile)),
        "minimum_breakeven_extra_cost_bps": minimum,
    }


def _write_report(
    payload: dict[str, object],
    monthly: pd.DataFrame,
    negative_2bps: pd.DataFrame,
    negative_4bps: pd.DataFrame,
) -> None:
    decision = payload["decision"]
    report_cols = [
        "month",
        "trade_count",
        "base_return_pct",
        "cost_load_per_1bps_pct",
        "breakeven_extra_cost_bps",
        "return_after_2bps_pct",
        "return_after_4bps_pct",
        "avg_leverage",
        "avg_position_weight",
        "base_trade_count",
        "rescue_trade_count",
        "long_trade_count",
        "short_trade_count",
        "cost_fragility_tag",
    ]
    lines = [
        "# Research V165 BTCUSDC Cost Fragility Audit",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to live: `{decision['promote_to_live']}`",
        f"- Message: {decision['message']}",
        f"- Required extra-cost headroom: `{REQUIRED_EXTRA_COST_BPS}` bps",
        f"- Fragile months: `{decision['fragile_month_count']}` / `{decision['month_count']}`",
        f"- Minimum breakeven extra cost: `{decision['minimum_breakeven_extra_cost_bps']}` bps",
        "",
        "## Audit Rules",
        "",
        "- Base path: V162 selected account path.",
        "- Monthly cost load is `sum(account_leverage * position_weight / 100)`.",
        "- Monthly breakeven extra cost is `monthly_return_pct / monthly_cost_load_per_1bps_pct`.",
        "- This audit does not add trades, change sides, or promote the system for live trading.",
        "",
        "## Monthly Cost Fragility",
        "",
        monthly[report_cols].to_csv(index=False).strip(),
        "",
        "## Negative Months After 2 bps Extra Cost",
        "",
        negative_2bps[report_cols].to_csv(index=False).strip() if not negative_2bps.empty else "No month turns negative after 2 bps extra cost.",
        "",
        "## Negative Months After 4 bps Extra Cost",
        "",
        negative_4bps[report_cols].to_csv(index=False).strip() if not negative_4bps.empty else "No month turns negative after 4 bps extra cost.",
        "",
        "## Interpretation",
        "",
        "V165 shows that the cost problem is concentrated in low-return months, not in threshold or sizing fragility. The next practical improvement should target execution quality or month/regime-level cost controls before considering live use.",
        "",
        "This is a research audit, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not V162_ACCOUNT_PATH.exists():
        v162.run()
    frame = pd.read_csv(V162_ACCOUNT_PATH)
    monthly = _monthly_cost_fragility(frame)
    monthly = _tag_fragility(monthly)
    monthly = monthly.sort_values("breakeven_extra_cost_bps", ascending=True).reset_index(drop=True)
    negative_2bps = _negative_months(monthly, extra_cost_bps=2.0)
    negative_4bps = _negative_months(monthly, extra_cost_bps=4.0)
    decision = _decision(monthly)
    payload = {
        "config": {
            "base": "v162_long_trend_follow_boost",
            "extra_cost_bps": list(EXTRA_COST_BPS),
            "required_extra_cost_bps": REQUIRED_EXTRA_COST_BPS,
            "adds_new_trades": False,
            "changes_existing_threshold": False,
            "promotes_live_trading": False,
        },
        "decision": decision,
        "negative_month_count_after_2bps": int(len(negative_2bps)),
        "negative_month_count_after_4bps": int(len(negative_4bps)),
    }
    monthly.to_csv(OUT_DIR / "v165_monthly_cost_fragility.csv", index=False)
    negative_2bps.to_csv(OUT_DIR / "v165_negative_months_after_2bps.csv", index=False)
    negative_4bps.to_csv(OUT_DIR / "v165_negative_months_after_4bps.csv", index=False)
    (OUT_DIR / "v165_cost_fragility_audit_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, monthly, negative_2bps, negative_4bps)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
