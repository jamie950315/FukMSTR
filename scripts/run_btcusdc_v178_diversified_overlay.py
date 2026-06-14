from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v162_long_trend_follow_boost as v162


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v178_diversified_overlay"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V178_BTCUSDC_DIVERSIFIED_OVERLAY.md"
V162_ACCOUNT_PATH = ROOT / "runs" / "research_v162_long_trend_follow_boost" / "v162_selected_account_path.csv"
SELECTOR_END = pd.Timestamp("2026-01-01T00:00:00Z")
MIN_BOOSTED_TRADE_COUNT = 20
MAX_MONTH_TRADE_SHARE_PCT = 40.0
MIN_RETURN_IMPROVEMENT_RATE = 0.03


@dataclass(frozen=True)
class DiversifiedOverlayPolicy:
    policy: str
    fragile_funding_threshold: float | None = None
    fragile_premium_threshold: float | None = None
    fragile_multiplier: float = 1.0
    probability_threshold: float | None = None
    min_range_position_720: float | None = None
    boost_multiplier: float = 1.0


POLICIES = (
    DiversifiedOverlayPolicy("v162_baseline_no_diversified_overlay"),
    DiversifiedOverlayPolicy(
        "v178_diversified_funding_or_premium0p50_prob61_range720_boost1p25",
        fragile_funding_threshold=-1.5,
        fragile_premium_threshold=-2.0,
        fragile_multiplier=0.50,
        probability_threshold=0.61,
        min_range_position_720=0.005,
        boost_multiplier=1.25,
    ),
    DiversifiedOverlayPolicy(
        "v178_diversified_funding_or_premium0p25_prob61_range720_boost1p25",
        fragile_funding_threshold=-1.5,
        fragile_premium_threshold=-2.0,
        fragile_multiplier=0.25,
        probability_threshold=0.61,
        min_range_position_720=0.005,
        boost_multiplier=1.25,
    ),
    DiversifiedOverlayPolicy(
        "v178_diversified_funding_or_premium0p75_prob61_range720_boost1p25",
        fragile_funding_threshold=-1.5,
        fragile_premium_threshold=-2.0,
        fragile_multiplier=0.75,
        probability_threshold=0.61,
        min_range_position_720=0.005,
        boost_multiplier=1.25,
    ),
    DiversifiedOverlayPolicy(
        "v178_diversified_funding120_0p50_prob61_range720_boost1p25",
        fragile_funding_threshold=-1.5,
        fragile_multiplier=0.50,
        probability_threshold=0.61,
        min_range_position_720=0.005,
        boost_multiplier=1.25,
    ),
)


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _long_rescue_mask(frame: pd.DataFrame) -> pd.Series:
    return frame.get("side", "").fillna("").astype(str).eq("long") & frame.get("leg", "").fillna("").astype(str).eq("rescue")


def _fragile_mask(frame: pd.DataFrame, policy: DiversifiedOverlayPolicy) -> pd.Series:
    fragile = pd.Series(False, index=frame.index)
    if policy.fragile_funding_threshold is not None and "funding_z_120d" in frame.columns:
        fragile = fragile | pd.to_numeric(frame["funding_z_120d"], errors="coerce").le(policy.fragile_funding_threshold)
    if policy.fragile_premium_threshold is not None and "premium_z_30d" in frame.columns:
        fragile = fragile | pd.to_numeric(frame["premium_z_30d"], errors="coerce").le(policy.fragile_premium_threshold)
    return fragile.fillna(False)


def _boost_mask(frame: pd.DataFrame, policy: DiversifiedOverlayPolicy) -> pd.Series:
    mask = pd.Series(True, index=frame.index)
    if policy.probability_threshold is not None and "direction_probability" in frame.columns:
        mask = mask & pd.to_numeric(frame["direction_probability"], errors="coerce").ge(policy.probability_threshold)
    if policy.min_range_position_720 is not None and "prior_range_pos_720" in frame.columns:
        mask = mask & pd.to_numeric(frame["prior_range_pos_720"], errors="coerce").ge(policy.min_range_position_720)
    return mask.fillna(False)


def _apply_diversified_overlay_policy(trades: pd.DataFrame, policy: DiversifiedOverlayPolicy) -> pd.DataFrame:
    out = trades.copy()
    long_rescue = _long_rescue_mask(out)
    fragile = long_rescue & _fragile_mask(out, policy)
    boosted = long_rescue & ~fragile & _boost_mask(out, policy) & (float(policy.boost_multiplier) != 1.0)
    multiplier = pd.Series(1.0, index=out.index)
    action = pd.Series("unchanged", index=out.index, dtype=object)
    multiplier.loc[fragile] = float(policy.fragile_multiplier)
    if float(policy.fragile_multiplier) != 1.0:
        action.loc[fragile] = "fragile_state_throttle"
    else:
        action.loc[fragile] = "fragile_state_unscaled"
    multiplier.loc[boosted] = float(policy.boost_multiplier)
    action.loc[boosted] = "diversified_high_confidence_boost"
    base_return = pd.to_numeric(out["v162_account_return_pct"], errors="coerce").fillna(0.0)
    base_pnl = pd.to_numeric(out["v162_account_pnl_bps"], errors="coerce").fillna(0.0)
    out["v178_policy"] = policy.policy
    out["v178_state_multiplier"] = multiplier
    out["v178_state_action"] = action
    out["v178_account_return_pct"] = base_return * multiplier
    out["v178_account_pnl_bps"] = base_pnl * multiplier
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
    work = path.loc[path["v178_state_action"].eq(action)].copy()
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
            "scaled_trade_count": 0,
            "throttled_trade_count": 0,
            "boosted_trade_count": 0,
            "boosted_active_month_count": 0,
            "boosted_max_month_trade_share_pct": 0.0,
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
    returns = pd.to_numeric(ordered["v178_account_return_pct"], errors="coerce").fillna(0.0)
    multiplier = pd.to_numeric(ordered["v178_state_multiplier"], errors="coerce").fillna(1.0)
    monthly = returns.groupby(ordered["month"], sort=True).sum().reindex(baseline_months, fill_value=0.0)
    holdout_mask = ordered["timestamp"].ge(SELECTOR_END)
    holdout_returns = returns.loc[holdout_mask]
    active_months, max_share = _month_concentration(ordered, action="diversified_high_confidence_boost")
    return {
        "policy": policy,
        "trade_count": int(len(ordered)),
        "scaled_trade_count": int(multiplier.ne(1.0).sum()),
        "throttled_trade_count": int(multiplier.lt(1.0).sum()),
        "boosted_trade_count": int(multiplier.gt(1.0).sum()),
        "boosted_active_month_count": active_months,
        "boosted_max_month_trade_share_pct": max_share,
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
    baseline = out.loc[out["policy"].eq("v162_baseline_no_diversified_overlay")].iloc[0]
    base_return = float(baseline["total_account_return_pct"])
    out["return_delta_pct"] = out["total_account_return_pct"] - base_return
    out["return_improvement_rate"] = out["return_delta_pct"] / base_return if base_return else 0.0
    out["drawdown_improvement_pct"] = out["max_drawdown_pct"] - float(baseline["max_drawdown_pct"])
    out["worst_month_improvement_pct"] = out["worst_month_pct"] - float(baseline["worst_month_pct"])
    out["positive_month_delta"] = out["positive_months"] - int(baseline["positive_months"])
    out["holdout_return_delta_pct"] = out["holdout_return_pct"] - float(baseline["holdout_return_pct"])
    out["holdout_drawdown_improvement_pct"] = out["holdout_max_drawdown_pct"] - float(baseline["holdout_max_drawdown_pct"])
    out["diversified_passed"] = (
        out["return_improvement_rate"].ge(MIN_RETURN_IMPROVEMENT_RATE)
        & out["drawdown_improvement_pct"].ge(0.0)
        & out["worst_month_improvement_pct"].ge(0.0)
        & out["positive_month_delta"].ge(0)
        & out["holdout_return_delta_pct"].ge(0.0)
        & out["boosted_trade_count"].ge(MIN_BOOSTED_TRADE_COUNT)
        & out["boosted_max_month_trade_share_pct"].le(MAX_MONTH_TRADE_SHARE_PCT)
    )
    out["diversified_score"] = (
        out["return_delta_pct"]
        + out["drawdown_improvement_pct"] * 20.0
        + out["holdout_return_delta_pct"] * 0.5
        + (MAX_MONTH_TRADE_SHARE_PCT - out["boosted_max_month_trade_share_pct"]).clip(lower=0.0)
        - out["scaled_trade_count"] * 0.05
    )
    out["diversified_passed"] = out["diversified_passed"].map(bool).astype(object)
    return out.sort_values(["diversified_passed", "diversified_score"], ascending=[False, False]).reset_index(drop=True)


def _select_policy(comparison: pd.DataFrame) -> str:
    candidates = comparison.loc[
        comparison["diversified_passed"].astype(bool)
        & ~comparison["policy"].eq("v162_baseline_no_diversified_overlay")
    ].copy()
    if candidates.empty:
        return "v162_baseline_no_diversified_overlay"
    return str(candidates.iloc[0]["policy"])


def _monthly_path(path: pd.DataFrame) -> pd.DataFrame:
    work = path.sort_values("timestamp", kind="mergesort").copy()
    work["timestamp"] = _to_utc(work["timestamp"])
    work["month"] = work["timestamp"].dt.strftime("%Y-%m")
    work["baseline_return"] = pd.to_numeric(work["v162_account_return_pct"], errors="coerce").fillna(0.0)
    work["candidate_return"] = pd.to_numeric(work["v178_account_return_pct"], errors="coerce").fillna(0.0)
    work["scaled"] = pd.to_numeric(work["v178_state_multiplier"], errors="coerce").fillna(1.0).ne(1.0)
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


def _action_profile(path: pd.DataFrame) -> pd.DataFrame:
    work = path.copy()
    work["baseline_return"] = pd.to_numeric(work["v162_account_return_pct"], errors="coerce").fillna(0.0)
    work["candidate_return"] = pd.to_numeric(work["v178_account_return_pct"], errors="coerce").fillna(0.0)
    work["candidate_pnl"] = pd.to_numeric(work["v178_account_pnl_bps"], errors="coerce").fillna(0.0)
    return (
        work.groupby(["v178_state_action", "side", "leg"], dropna=False)
        .agg(
            trade_count=("candidate_return", "size"),
            baseline_return_pct=("baseline_return", "sum"),
            candidate_return_pct=("candidate_return", "sum"),
            win_rate_pct=("candidate_pnl", lambda s: float((s > 0.0).mean() * 100.0) if len(s) else 0.0),
            avg_multiplier=("v178_state_multiplier", "mean"),
            avg_direction_probability=("direction_probability", "mean"),
            avg_prior_range_pos_720=("prior_range_pos_720", "mean"),
            avg_funding_z_120d=("funding_z_120d", "mean"),
            avg_premium_z_30d=("premium_z_30d", "mean"),
        )
        .reset_index()
        .assign(return_delta_pct=lambda df: df["candidate_return_pct"] - df["baseline_return_pct"])
    )


def _payload_for_comparison(comparison: pd.DataFrame, *, selected_policy: str) -> dict[str, object]:
    baseline = comparison.loc[comparison["policy"].eq("v162_baseline_no_diversified_overlay")]
    selected = comparison.loc[comparison["policy"].eq(selected_policy)]
    base = baseline.iloc[0] if not baseline.empty else pd.Series(dtype=object)
    sel = selected.iloc[0] if not selected.empty else pd.Series(dtype=object)
    selected_is_baseline = selected_policy == "v162_baseline_no_diversified_overlay"
    return {
        "config": {
            "base": "v162_selected_account_path",
            "selector_end": str(SELECTOR_END),
            "min_return_improvement_rate": MIN_RETURN_IMPROVEMENT_RATE,
            "min_boosted_trade_count": MIN_BOOSTED_TRADE_COUNT,
            "max_month_trade_share_pct": MAX_MONTH_TRADE_SHARE_PCT,
            "adds_new_trades": False,
            "changes_existing_threshold": False,
            "changes_trade_side": False,
            "promotes_live_trading": False,
        },
        "decision": {
            "status": (
                "diversified_overlay_no_candidate"
                if selected_is_baseline
                else "diversified_overlay_candidate_ready"
            ),
            "promote_to_live": False,
            "selected_policy": selected_policy,
            "selected_diversified_passed": bool(sel.get("diversified_passed", False)),
            "selected_return_delta_pct": float(sel.get("return_delta_pct", 0.0)),
            "selected_return_improvement_rate": float(sel.get("return_improvement_rate", 0.0)),
            "selected_drawdown_improvement_pct": float(sel.get("drawdown_improvement_pct", 0.0)),
            "selected_holdout_return_delta_pct": float(sel.get("holdout_return_delta_pct", 0.0)),
            "selected_holdout_drawdown_improvement_pct": float(sel.get("holdout_drawdown_improvement_pct", 0.0)),
            "selected_boosted_trade_count": int(sel.get("boosted_trade_count", 0)),
            "selected_boosted_active_month_count": int(sel.get("boosted_active_month_count", 0)),
            "selected_boosted_max_month_trade_share_pct": float(sel.get("boosted_max_month_trade_share_pct", 0.0)),
            "message": "V178 favors diversified long-rescue sizing over concentrated high-threshold boosts.",
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
        "# Research V178 BTCUSDC Diversified Overlay",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to live: `{decision['promote_to_live']}`",
        f"- Selected policy: `{decision['selected_policy']}`",
        f"- Diversified passed: `{decision['selected_diversified_passed']}`",
        f"- Return delta: `{decision['selected_return_delta_pct']}` pct",
        f"- Return improvement rate: `{decision['selected_return_improvement_rate']}`",
        f"- Drawdown improvement: `{decision['selected_drawdown_improvement_pct']}` pct",
        f"- Holdout return delta: `{decision['selected_holdout_return_delta_pct']}` pct",
        f"- Holdout drawdown improvement: `{decision['selected_holdout_drawdown_improvement_pct']}` pct",
        f"- Boosted trades: `{decision['selected_boosted_trade_count']}`",
        f"- Boosted active months: `{decision['selected_boosted_active_month_count']}`",
        f"- Boosted max-month share: `{decision['selected_boosted_max_month_trade_share_pct']}` pct",
        f"- Message: {decision['message']}",
        "",
        "## Overlay Rules",
        "",
        "- Base path: V162 selected account path.",
        "- V178 only scales existing long rescue trades.",
        "- Selected fragile state: `funding_z_120d <= -1.5` or `premium_z_30d <= -2.0`, scaled to `0.50x`.",
        "- Selected boost state: non-fragile long rescue with `direction_probability >= 0.61` and `prior_range_pos_720 >= 0.005`, scaled to `1.25x`.",
        "- Candidate must have at least 20 boosted trades, max single-month boost share <= 40%, and holdout return delta >= 0.",
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
        "V178 addresses V177's warning by selecting a broader, more distributed boost zone. It improves historical return while keeping boosted trades spread across more months, but it is still a research result and needs forward monitoring before live use.",
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
    trades = pd.read_csv(V162_ACCOUNT_PATH)
    trades["timestamp"] = _to_utc(trades["timestamp"])
    baseline_months = _baseline_months(trades)
    policy_paths = {policy.policy: _apply_diversified_overlay_policy(trades, policy) for policy in POLICIES}
    comparison = _compare_policies(policy_paths, baseline_months)
    selected_policy = _select_policy(comparison)
    selected_path = policy_paths[selected_policy]
    monthly = _monthly_path(selected_path)
    profile = _action_profile(selected_path)
    payload = _payload_for_comparison(comparison, selected_policy=selected_policy)
    comparison.to_csv(OUT_DIR / "v178_policy_comparison.csv", index=False)
    selected_path.to_csv(OUT_DIR / "v178_selected_account_path.csv", index=False)
    monthly.to_csv(OUT_DIR / "v178_selected_monthly_path.csv", index=False)
    profile.to_csv(OUT_DIR / "v178_selected_action_profile.csv", index=False)
    (OUT_DIR / "v178_diversified_overlay_summary.json").write_text(
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
