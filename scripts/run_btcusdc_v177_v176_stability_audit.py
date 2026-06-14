from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v176_combined_state_overlay as v176


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v177_v176_stability_audit"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V177_BTCUSDC_V176_STABILITY_AUDIT.md"
V176_ACCOUNT_PATH = ROOT / "runs" / "research_v176_combined_state_overlay" / "v176_selected_account_path.csv"
SELECTOR_END = pd.Timestamp("2026-01-01T00:00:00Z")
MIN_BOOSTED_TRADE_COUNT = 20
MAX_MONTH_TRADE_SHARE_PCT = 40.0


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _period_masks(frame: pd.DataFrame) -> dict[str, pd.Series]:
    timestamp = _to_utc(frame["timestamp"])
    return {
        "full": pd.Series(True, index=frame.index),
        "selector": timestamp < SELECTOR_END,
        "holdout": timestamp >= SELECTOR_END,
    }


def _max_drawdown(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    equity = returns.cumsum()
    drawdown = equity - equity.cummax()
    return float(drawdown.min()) if len(drawdown) else 0.0


def _period_metric_row(frame: pd.DataFrame, *, period: str) -> dict[str, object]:
    baseline_returns = pd.to_numeric(frame["v162_account_return_pct"], errors="coerce").fillna(0.0)
    candidate_returns = pd.to_numeric(frame["v176_account_return_pct"], errors="coerce").fillna(0.0)
    baseline_pnl = pd.to_numeric(frame["v162_account_pnl_bps"], errors="coerce").fillna(0.0)
    candidate_pnl = pd.to_numeric(frame["v176_account_pnl_bps"], errors="coerce").fillna(0.0)
    baseline_drawdown = _max_drawdown(baseline_returns)
    candidate_drawdown = _max_drawdown(candidate_returns)
    return {
        "period": period,
        "trade_count": int(len(frame)),
        "baseline_return_pct": float(baseline_returns.sum()),
        "candidate_return_pct": float(candidate_returns.sum()),
        "return_delta_pct": float(candidate_returns.sum() - baseline_returns.sum()),
        "baseline_max_drawdown_pct": baseline_drawdown,
        "candidate_max_drawdown_pct": candidate_drawdown,
        "drawdown_improvement_pct": candidate_drawdown - baseline_drawdown,
        "baseline_win_rate_pct": float((baseline_pnl > 0.0).mean() * 100.0) if len(baseline_pnl) else 0.0,
        "candidate_win_rate_pct": float((candidate_pnl > 0.0).mean() * 100.0) if len(candidate_pnl) else 0.0,
    }


def _period_stability_table(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    work["timestamp"] = _to_utc(work["timestamp"])
    masks = _period_masks(work)
    rows = [_period_metric_row(work.loc[mask].copy(), period=period) for period, mask in masks.items()]
    return pd.DataFrame(rows)


def _monthly_stability_table(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    work["timestamp"] = _to_utc(work["timestamp"])
    work["month"] = work["timestamp"].dt.strftime("%Y-%m")
    work["baseline_return"] = pd.to_numeric(work["v162_account_return_pct"], errors="coerce").fillna(0.0)
    work["candidate_return"] = pd.to_numeric(work["v176_account_return_pct"], errors="coerce").fillna(0.0)
    work["scaled"] = pd.to_numeric(work["v176_state_multiplier"], errors="coerce").fillna(1.0).ne(1.0)
    return (
        work.groupby("month", dropna=False)
        .agg(
            trade_count=("candidate_return", "size"),
            scaled_trade_count=("scaled", "sum"),
            baseline_return_pct=("baseline_return", "sum"),
            candidate_return_pct=("candidate_return", "sum"),
        )
        .reset_index()
        .assign(return_delta_pct=lambda df: df["candidate_return_pct"] - df["baseline_return_pct"])
    )


def _action_contribution_profile(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    work["timestamp"] = _to_utc(work["timestamp"])
    work["month"] = work["timestamp"].dt.strftime("%Y-%m")
    work["baseline_return"] = pd.to_numeric(work["v162_account_return_pct"], errors="coerce").fillna(0.0)
    work["candidate_return"] = pd.to_numeric(work["v176_account_return_pct"], errors="coerce").fillna(0.0)
    work["candidate_pnl"] = pd.to_numeric(work["v176_account_pnl_bps"], errors="coerce").fillna(0.0)
    rows: list[dict[str, object]] = []
    for action, group in work.groupby("v176_state_action", dropna=False):
        month_counts = group.groupby("month").size()
        max_month_share = float(month_counts.max() / len(group) * 100.0) if len(group) else 0.0
        rows.append(
            {
                "v176_state_action": str(action),
                "trade_count": int(len(group)),
                "active_month_count": int(group["month"].nunique()),
                "max_month_trade_share_pct": max_month_share,
                "baseline_return_pct": float(group["baseline_return"].sum()),
                "candidate_return_pct": float(group["candidate_return"].sum()),
                "return_delta_pct": float(group["candidate_return"].sum() - group["baseline_return"].sum()),
                "win_rate_pct": float((group["candidate_pnl"] > 0.0).mean() * 100.0) if len(group) else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values("return_delta_pct", ascending=False).reset_index(drop=True)


def _payload_for_audit(period_table: pd.DataFrame, action_profile: pd.DataFrame) -> dict[str, object]:
    boosted = action_profile.loc[action_profile["v176_state_action"].eq("nonfragile_high_confidence_boost")]
    boosted_count = int(boosted["trade_count"].sum()) if not boosted.empty else 0
    boosted_months = int(boosted["active_month_count"].sum()) if not boosted.empty else 0
    boosted_share = float(boosted["max_month_trade_share_pct"].max()) if not boosted.empty else 0.0
    full = period_table.loc[period_table["period"].eq("full")]
    holdout = period_table.loc[period_table["period"].eq("holdout")]
    full_row = full.iloc[0] if not full.empty else pd.Series(dtype=object)
    holdout_row = holdout.iloc[0] if not holdout.empty else pd.Series(dtype=object)
    small_boost_sample = boosted_count < MIN_BOOSTED_TRADE_COUNT
    concentrated_boost = boosted_share > MAX_MONTH_TRADE_SHARE_PCT
    holdout_return_positive = float(holdout_row.get("candidate_return_pct", 0.0)) > 0.0
    full_improved = (
        float(full_row.get("return_delta_pct", 0.0)) > 0.0
        and float(full_row.get("drawdown_improvement_pct", 0.0)) > 0.0
    )
    passed = bool(full_improved and holdout_return_positive and not small_boost_sample and not concentrated_boost)
    return {
        "config": {
            "base": "v176_selected_account_path",
            "selector_end": str(SELECTOR_END),
            "min_boosted_trade_count": MIN_BOOSTED_TRADE_COUNT,
            "max_month_trade_share_pct": MAX_MONTH_TRADE_SHARE_PCT,
            "adds_new_trades": False,
            "changes_existing_threshold": False,
            "changes_trade_side": False,
            "promotes_live_trading": False,
        },
        "decision": {
            "status": "v176_stability_passed" if passed else "v176_stability_warning",
            "promote_to_live": False,
            "boosted_trade_count": boosted_count,
            "boosted_active_month_count": boosted_months,
            "boosted_max_month_trade_share_pct": boosted_share,
            "small_boost_sample_risk": small_boost_sample,
            "concentrated_boost_risk": concentrated_boost,
            "full_return_delta_pct": float(full_row.get("return_delta_pct", 0.0)),
            "full_drawdown_improvement_pct": float(full_row.get("drawdown_improvement_pct", 0.0)),
            "holdout_candidate_return_pct": float(holdout_row.get("candidate_return_pct", 0.0)),
            "message": (
                "V176 passed the stability audit."
                if passed
                else "V176 historical improvement is promising but not stable enough to promote; keep forward monitoring."
            ),
        },
    }


def _write_report(
    payload: dict[str, object],
    period_table: pd.DataFrame,
    monthly_table: pd.DataFrame,
    action_profile: pd.DataFrame,
) -> None:
    decision = payload["decision"]
    lines = [
        "# Research V177 BTCUSDC V176 Stability Audit",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to live: `{decision['promote_to_live']}`",
        f"- Boosted trades: `{decision['boosted_trade_count']}`",
        f"- Boosted active months: `{decision['boosted_active_month_count']}`",
        f"- Boosted max-month share: `{decision['boosted_max_month_trade_share_pct']}` pct",
        f"- Small boost sample risk: `{decision['small_boost_sample_risk']}`",
        f"- Concentrated boost risk: `{decision['concentrated_boost_risk']}`",
        f"- Full return delta: `{decision['full_return_delta_pct']}` pct",
        f"- Full drawdown improvement: `{decision['full_drawdown_improvement_pct']}` pct",
        f"- Holdout candidate return: `{decision['holdout_candidate_return_pct']}` pct",
        f"- Message: {decision['message']}",
        "",
        "## Audit Rules",
        "",
        "- Base path: V176 selected account path.",
        "- Selector period: trades before 2026-01-01 UTC.",
        "- Holdout period: trades from 2026-01-01 UTC onward.",
        "- V177 does not add trades, change side, change thresholds, or promote live trading.",
        "",
        "## Period Stability",
        "",
        period_table.to_csv(index=False).strip(),
        "",
        "## Monthly Stability",
        "",
        monthly_table.to_csv(index=False).strip(),
        "",
        "## Action Contribution Profile",
        "",
        action_profile.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V177 audits whether V176's improvement is broad enough to trust as more than a small-sample historical effect. A warning means the result can guide research, but should not be promoted without forward evidence.",
        "",
        "This is a research audit, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not V176_ACCOUNT_PATH.exists():
        v176.run()
    frame = pd.read_csv(V176_ACCOUNT_PATH)
    frame["timestamp"] = _to_utc(frame["timestamp"])
    period_table = _period_stability_table(frame)
    monthly_table = _monthly_stability_table(frame)
    action_profile = _action_contribution_profile(frame)
    payload = _payload_for_audit(period_table, action_profile)
    period_table.to_csv(OUT_DIR / "v177_period_stability.csv", index=False)
    monthly_table.to_csv(OUT_DIR / "v177_monthly_stability.csv", index=False)
    action_profile.to_csv(OUT_DIR / "v177_action_contribution_profile.csv", index=False)
    (OUT_DIR / "v177_v176_stability_audit_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, period_table, monthly_table, action_profile)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
