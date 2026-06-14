from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v181_late_day_hard_throttle as v181


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v182_short_base_momentum_boost"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V182_BTCUSDC_SHORT_BASE_MOMENTUM_BOOST.md"
V181_ACCOUNT_PATH = ROOT / "runs" / "research_v181_late_day_hard_throttle" / "v181_selected_account_path.csv"
SELECTOR_END = pd.Timestamp("2026-01-01T00:00:00Z")
MIN_RETURN_DELTA_PCT = 10.0
MIN_HOLDOUT_RETURN_DELTA_PCT = 5.0
MIN_BOOSTED_TRADE_COUNT = 30
MIN_BOOSTED_ACTIVE_MONTHS = 10
MAX_MONTH_TRADE_SHARE_PCT = 25.0


@dataclass(frozen=True)
class ShortBaseMomentumBoostPolicy:
    policy: str
    min_trend_abs_720_bps: float | None = None
    min_funding_z_120d: float | None = None
    target_side: str = "short"
    target_leg: str = "base"
    require_v181_action: str = "unchanged"
    boost_multiplier: float = 1.0
    boost_action: str = "short_base_momentum_boost"


POLICIES = (
    ShortBaseMomentumBoostPolicy(
        "v181_baseline_no_short_base_momentum_boost",
        boost_multiplier=1.0,
        boost_action="unchanged",
    ),
    ShortBaseMomentumBoostPolicy(
        "v182_short_base_momentum_ge250_boost1p25",
        min_trend_abs_720_bps=250.0,
        boost_multiplier=1.25,
    ),
    ShortBaseMomentumBoostPolicy(
        "v182_short_base_momentum_ge200_boost1p25",
        min_trend_abs_720_bps=200.0,
        boost_multiplier=1.25,
    ),
    ShortBaseMomentumBoostPolicy(
        "v182_short_base_momentum_ge300_boost1p25",
        min_trend_abs_720_bps=300.0,
        boost_multiplier=1.25,
    ),
    ShortBaseMomentumBoostPolicy(
        "v182_short_base_momentum_ge250_boost1p15",
        min_trend_abs_720_bps=250.0,
        boost_multiplier=1.15,
    ),
    ShortBaseMomentumBoostPolicy(
        "v182_long_base_funding_ge1p038_boost1p25",
        min_funding_z_120d=1.038408,
        target_side="long",
        boost_multiplier=1.25,
        boost_action="long_base_funding_boost",
    ),
)


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _boost_mask(frame: pd.DataFrame, policy: ShortBaseMomentumBoostPolicy) -> pd.Series:
    if float(policy.boost_multiplier) == 1.0:
        return pd.Series(False, index=frame.index)
    mask = (
        frame.get("side", "").fillna("").astype(str).eq(policy.target_side)
        & frame.get("leg", "").fillna("").astype(str).eq(policy.target_leg)
        & frame.get("v181_state_action", "").fillna("").astype(str).eq(policy.require_v181_action)
    )
    if policy.min_trend_abs_720_bps is not None:
        trend = pd.to_numeric(frame.get("trend_abs_720_bps", pd.Series(index=frame.index)), errors="coerce")
        mask &= trend.ge(float(policy.min_trend_abs_720_bps))
    if policy.min_funding_z_120d is not None:
        funding = pd.to_numeric(frame.get("funding_z_120d", pd.Series(index=frame.index)), errors="coerce")
        mask &= funding.ge(float(policy.min_funding_z_120d))
    return mask.fillna(False)


def _apply_short_base_momentum_boost_policy(
    trades: pd.DataFrame,
    policy: ShortBaseMomentumBoostPolicy,
) -> pd.DataFrame:
    out = trades.copy()
    boosted = _boost_mask(out, policy)
    multiplier = pd.Series(1.0, index=out.index)
    action = pd.Series("unchanged", index=out.index, dtype=object)
    multiplier.loc[boosted] = float(policy.boost_multiplier)
    action.loc[boosted] = policy.boost_action
    base_return = pd.to_numeric(out["v181_account_return_pct"], errors="coerce").fillna(0.0)
    base_pnl = pd.to_numeric(out["v181_account_pnl_bps"], errors="coerce").fillna(0.0)
    out["v182_policy"] = policy.policy
    out["v182_state_multiplier"] = multiplier
    out["v182_state_action"] = action
    out["v182_account_return_pct"] = base_return * multiplier
    out["v182_account_pnl_bps"] = base_pnl * multiplier
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


def _month_concentration(path: pd.DataFrame) -> tuple[int, float]:
    work = path.loc[pd.to_numeric(path["v182_state_multiplier"], errors="coerce").fillna(1.0).gt(1.0)].copy()
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
    returns = pd.to_numeric(ordered["v182_account_return_pct"], errors="coerce").fillna(0.0)
    monthly = returns.groupby(ordered["month"], sort=True).sum().reindex(baseline_months, fill_value=0.0)
    holdout_mask = ordered["timestamp"].ge(SELECTOR_END)
    holdout_returns = returns.loc[holdout_mask]
    boosted = pd.to_numeric(ordered["v182_state_multiplier"], errors="coerce").fillna(1.0).gt(1.0)
    active_months, max_share = _month_concentration(ordered)
    return {
        "policy": policy,
        "trade_count": int(len(ordered)),
        "boosted_trade_count": int(boosted.sum()),
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
    baseline = out.loc[out["policy"].eq("v181_baseline_no_short_base_momentum_boost")].iloc[0]
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
    out["momentum_boost_passed"] = (
        out["return_delta_pct"].ge(MIN_RETURN_DELTA_PCT)
        & out["holdout_return_delta_pct"].ge(MIN_HOLDOUT_RETURN_DELTA_PCT)
        & out["drawdown_improvement_pct"].ge(0.0)
        & out["holdout_drawdown_improvement_pct"].ge(0.0)
        & out["worst_month_improvement_pct"].ge(0.0)
        & out["positive_month_delta"].ge(0)
        & out["boosted_trade_count"].ge(MIN_BOOSTED_TRADE_COUNT)
        & out["boosted_active_month_count"].ge(MIN_BOOSTED_ACTIVE_MONTHS)
        & out["boosted_max_month_trade_share_pct"].le(MAX_MONTH_TRADE_SHARE_PCT)
    )
    out["momentum_boost_score"] = (
        out["return_delta_pct"]
        + out["holdout_return_delta_pct"] * 1.5
        + out["drawdown_improvement_pct"] * 20.0
        + (MAX_MONTH_TRADE_SHARE_PCT - out["boosted_max_month_trade_share_pct"]).clip(lower=0.0)
        - out["boosted_trade_count"] * 0.15
    )
    out["momentum_boost_passed"] = out["momentum_boost_passed"].map(bool).astype(object)
    return out.sort_values(["momentum_boost_passed", "momentum_boost_score"], ascending=[False, False]).reset_index(
        drop=True
    )


def _select_policy(comparison: pd.DataFrame) -> str:
    candidates = comparison.loc[
        comparison["momentum_boost_passed"].astype(bool)
        & ~comparison["policy"].eq("v181_baseline_no_short_base_momentum_boost")
    ].copy()
    if candidates.empty:
        return "v181_baseline_no_short_base_momentum_boost"
    return str(candidates.iloc[0]["policy"])


def _monthly_path(path: pd.DataFrame) -> pd.DataFrame:
    work = path.sort_values("timestamp", kind="mergesort").copy()
    work["timestamp"] = _to_utc(work["timestamp"])
    work["month"] = work["timestamp"].dt.strftime("%Y-%m")
    work["baseline_return"] = pd.to_numeric(work["v181_account_return_pct"], errors="coerce").fillna(0.0)
    work["candidate_return"] = pd.to_numeric(work["v182_account_return_pct"], errors="coerce").fillna(0.0)
    work["boosted"] = pd.to_numeric(work["v182_state_multiplier"], errors="coerce").fillna(1.0).gt(1.0)
    return (
        work.groupby("month", dropna=False)
        .agg(
            trade_count=("candidate_return", "size"),
            boosted_trade_count=("boosted", "sum"),
            baseline_return_pct=("baseline_return", "sum"),
            candidate_return_pct=("candidate_return", "sum"),
        )
        .reset_index()
        .assign(return_delta_pct=lambda df: df["candidate_return_pct"] - df["baseline_return_pct"])
    )


def _action_profile(path: pd.DataFrame) -> pd.DataFrame:
    work = path.copy()
    work["baseline_return"] = pd.to_numeric(work["v181_account_return_pct"], errors="coerce").fillna(0.0)
    work["candidate_return"] = pd.to_numeric(work["v182_account_return_pct"], errors="coerce").fillna(0.0)
    work["candidate_pnl"] = pd.to_numeric(work["v182_account_pnl_bps"], errors="coerce").fillna(0.0)
    return (
        work.groupby(["v182_state_action", "side", "leg"], dropna=False)
        .agg(
            trade_count=("candidate_return", "size"),
            baseline_return_pct=("baseline_return", "sum"),
            candidate_return_pct=("candidate_return", "sum"),
            win_rate_pct=("candidate_pnl", lambda s: float((s > 0.0).mean() * 100.0) if len(s) else 0.0),
            avg_multiplier=("v182_state_multiplier", "mean"),
            avg_day_sofar_count=("day_sofar_count", "mean"),
            avg_prob_vs_day_sofar_max=("prob_vs_day_sofar_max", "mean"),
            avg_trend_abs_720_bps=("trend_abs_720_bps", "mean"),
            avg_funding_z_120d=("funding_z_120d", "mean"),
            avg_prior_range_pos_720=("prior_range_pos_720", "mean"),
        )
        .reset_index()
        .assign(return_delta_pct=lambda df: df["candidate_return_pct"] - df["baseline_return_pct"])
    )


def _payload_for_comparison(comparison: pd.DataFrame, *, selected_policy: str) -> dict[str, object]:
    selected = comparison.loc[comparison["policy"].eq(selected_policy)]
    sel = selected.iloc[0] if not selected.empty else pd.Series(dtype=object)
    selected_is_baseline = selected_policy == "v181_baseline_no_short_base_momentum_boost"
    return {
        "config": {
            "base": "v181_selected_account_path",
            "selector_end": str(SELECTOR_END),
            "min_return_delta_pct": MIN_RETURN_DELTA_PCT,
            "min_holdout_return_delta_pct": MIN_HOLDOUT_RETURN_DELTA_PCT,
            "min_boosted_trade_count": MIN_BOOSTED_TRADE_COUNT,
            "min_boosted_active_months": MIN_BOOSTED_ACTIVE_MONTHS,
            "max_month_trade_share_pct": MAX_MONTH_TRADE_SHARE_PCT,
            "adds_new_trades": False,
            "changes_existing_threshold": False,
            "changes_trade_side": False,
            "promotes_live_trading": False,
        },
        "decision": {
            "status": (
                "short_base_momentum_boost_no_candidate"
                if selected_is_baseline
                else "short_base_momentum_boost_candidate_ready"
            ),
            "promote_to_live": False,
            "selected_policy": selected_policy,
            "selected_momentum_boost_passed": bool(sel.get("momentum_boost_passed", False)),
            "selected_return_delta_pct": float(sel.get("return_delta_pct", 0.0)),
            "selected_return_improvement_rate": float(sel.get("return_improvement_rate", 0.0)),
            "selected_drawdown_improvement_pct": float(sel.get("drawdown_improvement_pct", 0.0)),
            "selected_holdout_return_delta_pct": float(sel.get("holdout_return_delta_pct", 0.0)),
            "selected_holdout_drawdown_improvement_pct": float(sel.get("holdout_drawdown_improvement_pct", 0.0)),
            "selected_boosted_trade_count": int(sel.get("boosted_trade_count", 0)),
            "selected_boosted_active_month_count": int(sel.get("boosted_active_month_count", 0)),
            "selected_boosted_max_month_trade_share_pct": float(sel.get("boosted_max_month_trade_share_pct", 0.0)),
            "message": "V182 tests whether high-momentum unchanged short-base rows deserve a modest size boost.",
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
        "# Research V182 BTCUSDC Short-Base Momentum Boost",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to live: `{decision['promote_to_live']}`",
        f"- Selected policy: `{decision['selected_policy']}`",
        f"- Momentum boost passed: `{decision['selected_momentum_boost_passed']}`",
        f"- Return delta vs V181: `{decision['selected_return_delta_pct']}` pct",
        f"- Return improvement rate vs V181: `{decision['selected_return_improvement_rate']}`",
        f"- Drawdown improvement vs V181: `{decision['selected_drawdown_improvement_pct']}` pct",
        f"- Holdout return delta vs V181: `{decision['selected_holdout_return_delta_pct']}` pct",
        f"- Holdout drawdown improvement vs V181: `{decision['selected_holdout_drawdown_improvement_pct']}` pct",
        f"- Boosted trades: `{decision['selected_boosted_trade_count']}`",
        f"- Boosted active months: `{decision['selected_boosted_active_month_count']}`",
        f"- Boosted max-month share: `{decision['selected_boosted_max_month_trade_share_pct']}` pct",
        f"- Message: {decision['message']}",
        "",
        "## Overlay Rules",
        "",
        "- Base path: V181 selected account path.",
        "- V182 does not add trades, change trade side, or change existing entry thresholds.",
        "- Selected candidate only boosts `side=short`, `leg=base`, `v181_state_action=unchanged` rows.",
        "- Selected high-momentum rule: `trend_abs_720_bps >= 250` with `1.25x` multiplier.",
        "- Candidate must improve full-path and holdout return, avoid worse drawdown/worst month, and keep boosted rows diversified across months.",
        "- The raw larger long-base funding candidate is kept in the comparison table but rejected unless it also passes the holdout gate.",
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
        "V182 treats trend and market state as sizing context rather than a primary direction signal. The selected policy boosts only the short-base rows that V181 left unchanged and where the 720-minute trend magnitude is already elevated.",
        "",
        "This remains a research audit, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not V181_ACCOUNT_PATH.exists():
        v181.run()
    trades = pd.read_csv(V181_ACCOUNT_PATH)
    trades["timestamp"] = _to_utc(trades["timestamp"])
    baseline_months = _baseline_months(trades)
    policy_paths = {policy.policy: _apply_short_base_momentum_boost_policy(trades, policy) for policy in POLICIES}
    comparison = _compare_policies(policy_paths, baseline_months)
    selected_policy = _select_policy(comparison)
    selected_path = policy_paths[selected_policy]
    monthly = _monthly_path(selected_path)
    profile = _action_profile(selected_path)
    payload = _payload_for_comparison(comparison, selected_policy=selected_policy)
    comparison.to_csv(OUT_DIR / "v182_policy_comparison.csv", index=False)
    selected_path.to_csv(OUT_DIR / "v182_selected_account_path.csv", index=False)
    monthly.to_csv(OUT_DIR / "v182_selected_monthly_path.csv", index=False)
    profile.to_csv(OUT_DIR / "v182_selected_action_profile.csv", index=False)
    (OUT_DIR / "v182_short_base_momentum_boost_summary.json").write_text(
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
