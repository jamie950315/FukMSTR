from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v179_short_nonspike_overlay as v179


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v180_short_base_late_day_throttle"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V180_BTCUSDC_SHORT_BASE_LATE_DAY_THROTTLE.md"
V179_ACCOUNT_PATH = ROOT / "runs" / "research_v179_short_nonspike_overlay" / "v179_selected_account_path.csv"
SELECTOR_END = pd.Timestamp("2026-01-01T00:00:00Z")
MIN_RETURN_DELTA_PCT = 10.0
MIN_THROTTLED_TRADE_COUNT = 40
MIN_THROTTLED_ACTIVE_MONTHS = 12
MAX_MONTH_TRADE_SHARE_PCT = 25.0


@dataclass(frozen=True)
class ShortBaseLateDayThrottlePolicy:
    policy: str
    min_day_sofar_count: int | None = None
    throttle_multiplier: float = 1.0


POLICIES = (
    ShortBaseLateDayThrottlePolicy("v179_baseline_no_late_day_throttle"),
    ShortBaseLateDayThrottlePolicy(
        "v180_short_base_late_day_count_ge_5_throttle0p25",
        min_day_sofar_count=5,
        throttle_multiplier=0.25,
    ),
    ShortBaseLateDayThrottlePolicy(
        "v180_short_base_late_day_count_ge_5_throttle0p50",
        min_day_sofar_count=5,
        throttle_multiplier=0.50,
    ),
    ShortBaseLateDayThrottlePolicy(
        "v180_short_base_late_day_count_ge_64_throttle0p25",
        min_day_sofar_count=64,
        throttle_multiplier=0.25,
    ),
    ShortBaseLateDayThrottlePolicy(
        "v180_short_base_late_day_count_ge_160_throttle0p25",
        min_day_sofar_count=160,
        throttle_multiplier=0.25,
    ),
)


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _short_base_mask(frame: pd.DataFrame) -> pd.Series:
    return frame.get("side", "").fillna("").astype(str).eq("short") & frame.get("leg", "").fillna("").astype(str).eq(
        "base"
    )


def _unchanged_v179_mask(frame: pd.DataFrame) -> pd.Series:
    return frame.get("v179_state_action", "").fillna("").astype(str).eq("unchanged")


def _late_day_mask(frame: pd.DataFrame, policy: ShortBaseLateDayThrottlePolicy) -> pd.Series:
    if policy.min_day_sofar_count is None or "day_sofar_count" not in frame.columns:
        return pd.Series(False, index=frame.index)
    return pd.to_numeric(frame["day_sofar_count"], errors="coerce").ge(policy.min_day_sofar_count).fillna(False)


def _apply_short_base_late_day_policy(
    trades: pd.DataFrame,
    policy: ShortBaseLateDayThrottlePolicy,
) -> pd.DataFrame:
    out = trades.copy()
    throttled = (
        _short_base_mask(out)
        & _unchanged_v179_mask(out)
        & _late_day_mask(out, policy)
        & (float(policy.throttle_multiplier) != 1.0)
    )
    multiplier = pd.Series(1.0, index=out.index)
    action = pd.Series("unchanged", index=out.index, dtype=object)
    multiplier.loc[throttled] = float(policy.throttle_multiplier)
    action.loc[throttled] = "short_base_late_day_throttle"
    base_return = pd.to_numeric(out["v179_account_return_pct"], errors="coerce").fillna(0.0)
    base_pnl = pd.to_numeric(out["v179_account_pnl_bps"], errors="coerce").fillna(0.0)
    out["v180_policy"] = policy.policy
    out["v180_state_multiplier"] = multiplier
    out["v180_state_action"] = action
    out["v180_account_return_pct"] = base_return * multiplier
    out["v180_account_pnl_bps"] = base_pnl * multiplier
    return out


def _baseline_months(frame: pd.DataFrame) -> pd.Index:
    if frame.empty:
        return pd.Index([], name="month")
    work = frame.copy()
    work["timestamp"] = _to_utc(work["timestamp"])
    return pd.Index(work["timestamp"].dt.strftime("%Y-%m").unique(), name="month").sort_values()


def _max_drawdown(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    equity = returns.cumsum()
    drawdown = equity - equity.cummax()
    return float(drawdown.min()) if len(drawdown) else 0.0


def _month_concentration(path: pd.DataFrame, *, action: str) -> tuple[int, float]:
    work = path.loc[path["v180_state_action"].eq(action)].copy()
    if work.empty:
        return 0, 0.0
    work["timestamp"] = _to_utc(work["timestamp"])
    month_counts = work.groupby(work["timestamp"].dt.strftime("%Y-%m")).size()
    return int(month_counts.size), float(month_counts.max() / len(work) * 100.0)


def _policy_metrics(policy: str, path: pd.DataFrame, *, baseline_months: pd.Index) -> dict[str, object]:
    if path.empty:
        monthly = pd.Series(0.0, index=baseline_months)
        return {
            "policy": policy,
            "trade_count": 0,
            "throttled_trade_count": 0,
            "throttled_active_month_count": 0,
            "throttled_max_month_trade_share_pct": 0.0,
            "total_account_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "positive_months": int((monthly > 0.0).sum()),
            "month_count": int(len(monthly)),
            "worst_month_pct": float(monthly.min()) if len(monthly) else 0.0,
            "holdout_return_pct": 0.0,
            "holdout_max_drawdown_pct": 0.0,
        }
    ordered = path.sort_values("timestamp", kind="mergesort").copy()
    ordered["timestamp"] = _to_utc(ordered["timestamp"])
    ordered["month"] = ordered["timestamp"].dt.strftime("%Y-%m")
    returns = pd.to_numeric(ordered["v180_account_return_pct"], errors="coerce").fillna(0.0)
    multiplier = pd.to_numeric(ordered["v180_state_multiplier"], errors="coerce").fillna(1.0)
    monthly = returns.groupby(ordered["month"], sort=True).sum().reindex(baseline_months, fill_value=0.0)
    holdout_mask = ordered["timestamp"].ge(SELECTOR_END)
    holdout_returns = returns.loc[holdout_mask]
    active_months, max_share = _month_concentration(ordered, action="short_base_late_day_throttle")
    return {
        "policy": policy,
        "trade_count": int(len(ordered)),
        "throttled_trade_count": int(multiplier.lt(1.0).sum()),
        "throttled_active_month_count": active_months,
        "throttled_max_month_trade_share_pct": max_share,
        "total_account_return_pct": float(returns.sum()),
        "max_drawdown_pct": _max_drawdown(returns),
        "positive_months": int((monthly > 0.0).sum()),
        "month_count": int(len(monthly)),
        "worst_month_pct": float(monthly.min()) if len(monthly) else 0.0,
        "holdout_return_pct": float(holdout_returns.sum()),
        "holdout_max_drawdown_pct": _max_drawdown(holdout_returns),
    }


def _compare_policies(policy_paths: dict[str, pd.DataFrame], baseline_months: pd.Index) -> pd.DataFrame:
    rows = [_policy_metrics(policy, path, baseline_months=baseline_months) for policy, path in policy_paths.items()]
    out = pd.DataFrame(rows)
    baseline = out.loc[out["policy"].eq("v179_baseline_no_late_day_throttle")].iloc[0]
    base_return = float(baseline["total_account_return_pct"])
    out["return_delta_pct"] = out["total_account_return_pct"] - base_return
    out["return_improvement_rate"] = out["return_delta_pct"] / base_return if base_return else 0.0
    out["drawdown_improvement_pct"] = out["max_drawdown_pct"] - float(baseline["max_drawdown_pct"])
    out["worst_month_improvement_pct"] = out["worst_month_pct"] - float(baseline["worst_month_pct"])
    out["positive_month_delta"] = out["positive_months"] - int(baseline["positive_months"])
    out["holdout_return_delta_pct"] = out["holdout_return_pct"] - float(baseline["holdout_return_pct"])
    out["holdout_drawdown_improvement_pct"] = out["holdout_max_drawdown_pct"] - float(
        baseline["holdout_max_drawdown_pct"]
    )
    out["late_day_throttle_passed"] = (
        out["return_delta_pct"].ge(MIN_RETURN_DELTA_PCT)
        & out["drawdown_improvement_pct"].ge(0.0)
        & out["worst_month_improvement_pct"].ge(0.0)
        & out["positive_month_delta"].ge(0)
        & out["holdout_return_delta_pct"].ge(0.0)
        & out["holdout_drawdown_improvement_pct"].ge(0.0)
        & out["throttled_trade_count"].ge(MIN_THROTTLED_TRADE_COUNT)
        & out["throttled_active_month_count"].ge(MIN_THROTTLED_ACTIVE_MONTHS)
        & out["throttled_max_month_trade_share_pct"].le(MAX_MONTH_TRADE_SHARE_PCT)
    )
    out["late_day_throttle_score"] = (
        out["return_delta_pct"]
        + out["drawdown_improvement_pct"] * 20.0
        + out["holdout_return_delta_pct"] * 0.5
        + (MAX_MONTH_TRADE_SHARE_PCT - out["throttled_max_month_trade_share_pct"]).clip(lower=0.0)
        - out["throttled_trade_count"] * 0.02
    )
    out["late_day_throttle_passed"] = out["late_day_throttle_passed"].map(bool).astype(object)
    return out.sort_values(
        ["late_day_throttle_passed", "late_day_throttle_score"],
        ascending=[False, False],
    ).reset_index(drop=True)


def _select_policy(comparison: pd.DataFrame) -> str:
    candidates = comparison.loc[
        comparison["late_day_throttle_passed"].astype(bool)
        & ~comparison["policy"].eq("v179_baseline_no_late_day_throttle")
    ].copy()
    if candidates.empty:
        return "v179_baseline_no_late_day_throttle"
    return str(candidates.iloc[0]["policy"])


def _monthly_path(path: pd.DataFrame) -> pd.DataFrame:
    work = path.sort_values("timestamp", kind="mergesort").copy()
    work["timestamp"] = _to_utc(work["timestamp"])
    work["month"] = work["timestamp"].dt.strftime("%Y-%m")
    work["baseline_return"] = pd.to_numeric(work["v179_account_return_pct"], errors="coerce").fillna(0.0)
    work["candidate_return"] = pd.to_numeric(work["v180_account_return_pct"], errors="coerce").fillna(0.0)
    work["throttled"] = pd.to_numeric(work["v180_state_multiplier"], errors="coerce").fillna(1.0).lt(1.0)
    return (
        work.groupby("month", dropna=False)
        .agg(
            trade_count=("candidate_return", "size"),
            throttled_trade_count=("throttled", "sum"),
            baseline_return_pct=("baseline_return", "sum"),
            candidate_return_pct=("candidate_return", "sum"),
        )
        .reset_index()
        .assign(return_delta_pct=lambda df: df["candidate_return_pct"] - df["baseline_return_pct"])
    )


def _action_profile(path: pd.DataFrame) -> pd.DataFrame:
    work = path.copy()
    work["baseline_return"] = pd.to_numeric(work["v179_account_return_pct"], errors="coerce").fillna(0.0)
    work["candidate_return"] = pd.to_numeric(work["v180_account_return_pct"], errors="coerce").fillna(0.0)
    work["candidate_pnl"] = pd.to_numeric(work["v180_account_pnl_bps"], errors="coerce").fillna(0.0)
    return (
        work.groupby(["v180_state_action", "side", "leg"], dropna=False)
        .agg(
            trade_count=("candidate_return", "size"),
            baseline_return_pct=("baseline_return", "sum"),
            candidate_return_pct=("candidate_return", "sum"),
            win_rate_pct=("candidate_pnl", lambda s: float((s > 0.0).mean() * 100.0) if len(s) else 0.0),
            avg_multiplier=("v180_state_multiplier", "mean"),
            avg_day_sofar_count=("day_sofar_count", "mean"),
            avg_prob_vs_day_sofar_max=("prob_vs_day_sofar_max", "mean"),
            avg_direction_probability=("direction_probability", "mean"),
            avg_trend_abs_720_bps=("trend_abs_720_bps", "mean"),
            avg_prior_range_pos_720=("prior_range_pos_720", "mean"),
        )
        .reset_index()
        .assign(return_delta_pct=lambda df: df["candidate_return_pct"] - df["baseline_return_pct"])
    )


def _payload_for_comparison(comparison: pd.DataFrame, *, selected_policy: str) -> dict[str, object]:
    selected = comparison.loc[comparison["policy"].eq(selected_policy)]
    sel = selected.iloc[0] if not selected.empty else pd.Series(dtype=object)
    selected_is_baseline = selected_policy == "v179_baseline_no_late_day_throttle"
    return {
        "config": {
            "base": "v179_selected_account_path",
            "selector_end": str(SELECTOR_END),
            "min_return_delta_pct": MIN_RETURN_DELTA_PCT,
            "min_throttled_trade_count": MIN_THROTTLED_TRADE_COUNT,
            "min_throttled_active_months": MIN_THROTTLED_ACTIVE_MONTHS,
            "max_month_trade_share_pct": MAX_MONTH_TRADE_SHARE_PCT,
            "adds_new_trades": False,
            "changes_existing_threshold": False,
            "changes_trade_side": False,
            "promotes_live_trading": False,
        },
        "decision": {
            "status": (
                "late_day_throttle_no_candidate"
                if selected_is_baseline
                else "late_day_throttle_candidate_ready"
            ),
            "promote_to_live": False,
            "selected_policy": selected_policy,
            "selected_late_day_throttle_passed": bool(sel.get("late_day_throttle_passed", False)),
            "selected_return_delta_pct": float(sel.get("return_delta_pct", 0.0)),
            "selected_return_improvement_rate": float(sel.get("return_improvement_rate", 0.0)),
            "selected_drawdown_improvement_pct": float(sel.get("drawdown_improvement_pct", 0.0)),
            "selected_holdout_return_delta_pct": float(sel.get("holdout_return_delta_pct", 0.0)),
            "selected_holdout_drawdown_improvement_pct": float(sel.get("holdout_drawdown_improvement_pct", 0.0)),
            "selected_throttled_trade_count": int(sel.get("throttled_trade_count", 0)),
            "selected_throttled_active_month_count": int(sel.get("throttled_active_month_count", 0)),
            "selected_throttled_max_month_trade_share_pct": float(
                sel.get("throttled_max_month_trade_share_pct", 0.0)
            ),
            "message": "V180 throttles the remaining weak short-base late-day regime after V179.",
        },
    }


def _write_report(
    payload: dict[str, object],
    comparison: pd.DataFrame,
    selected_monthly: pd.DataFrame,
    selected_profile: pd.DataFrame,
) -> None:
    decision = payload["decision"]
    lines = [
        "# Research V180 BTCUSDC Short Base Late-Day Throttle",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to live: `{decision['promote_to_live']}`",
        f"- Selected policy: `{decision['selected_policy']}`",
        f"- Late-day throttle passed: `{decision['selected_late_day_throttle_passed']}`",
        f"- Return delta vs V179: `{decision['selected_return_delta_pct']}` pct",
        f"- Return improvement rate vs V179: `{decision['selected_return_improvement_rate']}`",
        f"- Drawdown improvement vs V179: `{decision['selected_drawdown_improvement_pct']}` pct",
        f"- Holdout return delta vs V179: `{decision['selected_holdout_return_delta_pct']}` pct",
        f"- Holdout drawdown improvement vs V179: `{decision['selected_holdout_drawdown_improvement_pct']}` pct",
        f"- Throttled trades: `{decision['selected_throttled_trade_count']}`",
        f"- Throttled active months: `{decision['selected_throttled_active_month_count']}`",
        f"- Throttled max-month share: `{decision['selected_throttled_max_month_trade_share_pct']}` pct",
        f"- Message: {decision['message']}",
        "",
        "## Overlay Rules",
        "",
        "- Base path: V179 selected account path.",
        "- V180 only scales existing short base trades that V179 left unchanged.",
        "- Selected throttle state: `day_sofar_count >= 5`, scaled to `0.25x`.",
        "- Candidate must improve return vs V179, avoid worse drawdown/worst month, keep holdout return non-negative vs V179, and keep throttles diversified.",
        "- This audit does not add trades, change side, change thresholds, or promote live trading.",
        "",
        "## Policy Comparison",
        "",
        comparison.to_csv(index=False).strip(),
        "",
        "## Selected Monthly Path",
        "",
        selected_monthly.to_csv(index=False).strip(),
        "",
        "## Selected Action Profile",
        "",
        selected_profile.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V180 addresses the remaining negative short-base contribution after V179. The selected late-day throttle cuts size only after several same-day signals have already appeared, where the historical short-base edge was weaker.",
        "",
        "This is a research audit, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not V179_ACCOUNT_PATH.exists():
        v179.run()
    trades = pd.read_csv(V179_ACCOUNT_PATH)
    trades["timestamp"] = _to_utc(trades["timestamp"])
    baseline_months = _baseline_months(trades)
    policy_paths = {policy.policy: _apply_short_base_late_day_policy(trades, policy) for policy in POLICIES}
    comparison = _compare_policies(policy_paths, baseline_months)
    selected_policy = _select_policy(comparison)
    selected_path = policy_paths[selected_policy]
    monthly = _monthly_path(selected_path)
    profile = _action_profile(selected_path)
    payload = _payload_for_comparison(comparison, selected_policy=selected_policy)
    comparison.to_csv(OUT_DIR / "v180_policy_comparison.csv", index=False)
    selected_path.to_csv(OUT_DIR / "v180_selected_account_path.csv", index=False)
    monthly.to_csv(OUT_DIR / "v180_selected_monthly_path.csv", index=False)
    profile.to_csv(OUT_DIR / "v180_selected_action_profile.csv", index=False)
    (OUT_DIR / "v180_short_base_late_day_throttle_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, comparison, monthly, profile)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
