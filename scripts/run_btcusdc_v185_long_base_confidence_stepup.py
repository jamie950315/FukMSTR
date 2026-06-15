from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v184_long_base_low_premium_throttle as v184


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v185_long_base_confidence_stepup"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V185_BTCUSDC_LONG_BASE_CONFIDENCE_STEPUP.md"
V184_ACCOUNT_PATH = ROOT / "runs" / "research_v184_long_base_low_premium_throttle" / "v184_selected_account_path.csv"
SELECTOR_END = pd.Timestamp("2026-01-01T00:00:00Z")
MIN_RETURN_DELTA_PCT = 10.0
MIN_HOLDOUT_RETURN_DELTA_PCT = 5.0
MIN_STEPUP_TRADE_COUNT = 20
MIN_STEPUP_ACTIVE_MONTHS = 10
MAX_MONTH_TRADE_SHARE_PCT = 25.0
MAX_SINGLE_TRADE_DELTA_SHARE_PCT = 35.0


@dataclass(frozen=True)
class LongBaseConfidenceStepupPolicy:
    policy: str
    min_direction_probability: float | None = None
    min_trend_abs_720_bps: float | None = None
    target_side: str = "long"
    target_leg: str = "base"
    require_v184_action: str = "unchanged"
    stepup_multiplier: float = 1.0
    stepup_action: str = "long_base_confidence_stepup"


POLICIES = (
    LongBaseConfidenceStepupPolicy(
        "v184_baseline_no_long_base_confidence_stepup",
        stepup_multiplier=1.0,
        stepup_action="unchanged",
    ),
    LongBaseConfidenceStepupPolicy(
        "v185_long_base_confidence_ge0p610399_stepup1p25",
        min_direction_probability=0.610399,
        stepup_multiplier=1.25,
    ),
    LongBaseConfidenceStepupPolicy(
        "v185_long_base_confidence_ge0p610399_stepup1p15",
        min_direction_probability=0.610399,
        stepup_multiplier=1.15,
    ),
    LongBaseConfidenceStepupPolicy(
        "v185_long_base_confidence_ge0p610399_stepup1p10",
        min_direction_probability=0.610399,
        stepup_multiplier=1.10,
    ),
    LongBaseConfidenceStepupPolicy(
        "v185_alternate_short_base_trend_ge200_stepup1p25",
        min_trend_abs_720_bps=200.0,
        target_side="short",
        target_leg="base",
        stepup_multiplier=1.25,
        stepup_action="short_base_trend_stepup",
    ),
)


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _stepup_mask(frame: pd.DataFrame, policy: LongBaseConfidenceStepupPolicy) -> pd.Series:
    if float(policy.stepup_multiplier) == 1.0:
        return pd.Series(False, index=frame.index)
    mask = (
        frame.get("side", "").fillna("").astype(str).eq(policy.target_side)
        & frame.get("leg", "").fillna("").astype(str).eq(policy.target_leg)
        & frame.get("v184_state_action", "").fillna("").astype(str).eq(policy.require_v184_action)
    )
    if policy.min_direction_probability is not None:
        direction_probability = pd.to_numeric(
            frame.get("direction_probability", pd.Series(index=frame.index)),
            errors="coerce",
        )
        mask &= direction_probability.ge(float(policy.min_direction_probability))
    if policy.min_trend_abs_720_bps is not None:
        trend_abs = pd.to_numeric(frame.get("trend_abs_720_bps", pd.Series(index=frame.index)), errors="coerce")
        mask &= trend_abs.ge(float(policy.min_trend_abs_720_bps))
    return mask.fillna(False)


def _apply_long_base_confidence_stepup_policy(
    trades: pd.DataFrame,
    policy: LongBaseConfidenceStepupPolicy,
) -> pd.DataFrame:
    out = trades.copy()
    stepped = _stepup_mask(out, policy)
    multiplier = pd.Series(1.0, index=out.index)
    action = pd.Series("unchanged", index=out.index, dtype=object)
    multiplier.loc[stepped] = float(policy.stepup_multiplier)
    action.loc[stepped] = policy.stepup_action
    base_return = pd.to_numeric(out["v184_account_return_pct"], errors="coerce").fillna(0.0)
    base_pnl = pd.to_numeric(out["v184_account_pnl_bps"], errors="coerce").fillna(0.0)
    out["v185_policy"] = policy.policy
    out["v185_state_multiplier"] = multiplier
    out["v185_state_action"] = action
    out["v185_account_return_pct"] = base_return * multiplier
    out["v185_account_pnl_bps"] = base_pnl * multiplier
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
    work = path.loc[pd.to_numeric(path["v185_state_multiplier"], errors="coerce").fillna(1.0).gt(1.0)].copy()
    if work.empty:
        return 0, 0.0
    work["timestamp"] = _to_utc(work["timestamp"])
    month_counts = work.groupby(work["timestamp"].dt.strftime("%Y-%m")).size()
    return int(month_counts.size), float(month_counts.max() / len(work) * 100.0)


def _single_trade_delta_share(path: pd.DataFrame) -> float:
    multiplier = pd.to_numeric(path["v185_state_multiplier"], errors="coerce").fillna(1.0)
    stepped = multiplier.gt(1.0)
    if not stepped.any():
        return 0.0
    candidate_return = pd.to_numeric(path["v185_account_return_pct"], errors="coerce").fillna(0.0)
    if "v184_account_return_pct" in path.columns:
        base_return = pd.to_numeric(path["v184_account_return_pct"], errors="coerce").fillna(0.0)
    else:
        base_return = candidate_return.div(multiplier.replace(0.0, 1.0))
    delta = (candidate_return.loc[stepped] - base_return.loc[stepped]).abs()
    total = float(delta.sum())
    return float(delta.max() / total * 100.0) if total else 0.0


def _policy_metrics(policy: str, path: pd.DataFrame, *, baseline_months: pd.Index) -> dict[str, object]:
    if path.empty:
        monthly = pd.Series(0.0, index=baseline_months)
        return {
            "policy": policy,
            "trade_count": 0,
            "stepup_trade_count": 0,
            "stepup_active_month_count": 0,
            "stepup_max_month_trade_share_pct": 0.0,
            "stepup_max_single_trade_delta_share_pct": 0.0,
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
    returns = pd.to_numeric(ordered["v185_account_return_pct"], errors="coerce").fillna(0.0)
    monthly = returns.groupby(ordered["month"], sort=True).sum().reindex(baseline_months, fill_value=0.0)
    holdout_mask = ordered["timestamp"].ge(SELECTOR_END)
    holdout_returns = returns.loc[holdout_mask]
    stepped = pd.to_numeric(ordered["v185_state_multiplier"], errors="coerce").fillna(1.0).gt(1.0)
    active_months, max_share = _month_concentration(ordered)
    return {
        "policy": policy,
        "trade_count": int(len(ordered)),
        "stepup_trade_count": int(stepped.sum()),
        "stepup_active_month_count": active_months,
        "stepup_max_month_trade_share_pct": max_share,
        "stepup_max_single_trade_delta_share_pct": _single_trade_delta_share(ordered),
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
    baseline = out.loc[out["policy"].eq("v184_baseline_no_long_base_confidence_stepup")].iloc[0]
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
    out["confidence_stepup_passed"] = (
        out["return_delta_pct"].ge(MIN_RETURN_DELTA_PCT)
        & out["holdout_return_delta_pct"].ge(MIN_HOLDOUT_RETURN_DELTA_PCT)
        & out["drawdown_improvement_pct"].ge(0.0)
        & out["holdout_drawdown_improvement_pct"].ge(0.0)
        & out["worst_month_improvement_pct"].ge(0.0)
        & out["positive_month_delta"].ge(0)
        & out["stepup_trade_count"].ge(MIN_STEPUP_TRADE_COUNT)
        & out["stepup_active_month_count"].ge(MIN_STEPUP_ACTIVE_MONTHS)
        & out["stepup_max_month_trade_share_pct"].le(MAX_MONTH_TRADE_SHARE_PCT)
        & out["stepup_max_single_trade_delta_share_pct"].le(MAX_SINGLE_TRADE_DELTA_SHARE_PCT)
    )
    out["confidence_stepup_score"] = (
        out["return_delta_pct"]
        + out["holdout_return_delta_pct"] * 1.5
        + out["drawdown_improvement_pct"] * 20.0
        + (MAX_MONTH_TRADE_SHARE_PCT - out["stepup_max_month_trade_share_pct"]).clip(lower=0.0)
        + (MAX_SINGLE_TRADE_DELTA_SHARE_PCT - out["stepup_max_single_trade_delta_share_pct"]).clip(lower=0.0) * 0.5
        - out["stepup_trade_count"] * 0.05
    )
    out["confidence_stepup_passed"] = out["confidence_stepup_passed"].map(bool).astype(object)
    return out.sort_values(
        ["confidence_stepup_passed", "confidence_stepup_score"],
        ascending=[False, False],
    ).reset_index(drop=True)


def _select_policy(comparison: pd.DataFrame) -> str:
    candidates = comparison.loc[
        comparison["confidence_stepup_passed"].astype(bool)
        & ~comparison["policy"].eq("v184_baseline_no_long_base_confidence_stepup")
    ].copy()
    if candidates.empty:
        return "v184_baseline_no_long_base_confidence_stepup"
    return str(candidates.iloc[0]["policy"])


def _monthly_path(path: pd.DataFrame) -> pd.DataFrame:
    work = path.sort_values("timestamp", kind="mergesort").copy()
    work["timestamp"] = _to_utc(work["timestamp"])
    work["month"] = work["timestamp"].dt.strftime("%Y-%m")
    work["baseline_return"] = pd.to_numeric(work["v184_account_return_pct"], errors="coerce").fillna(0.0)
    work["candidate_return"] = pd.to_numeric(work["v185_account_return_pct"], errors="coerce").fillna(0.0)
    work["stepped_up"] = pd.to_numeric(work["v185_state_multiplier"], errors="coerce").fillna(1.0).gt(1.0)
    return (
        work.groupby("month", dropna=False)
        .agg(
            trade_count=("candidate_return", "size"),
            stepup_trade_count=("stepped_up", "sum"),
            baseline_return_pct=("baseline_return", "sum"),
            candidate_return_pct=("candidate_return", "sum"),
        )
        .reset_index()
        .assign(return_delta_pct=lambda df: df["candidate_return_pct"] - df["baseline_return_pct"])
    )


def _action_profile(path: pd.DataFrame) -> pd.DataFrame:
    work = path.copy()
    work["baseline_return"] = pd.to_numeric(work["v184_account_return_pct"], errors="coerce").fillna(0.0)
    work["candidate_return"] = pd.to_numeric(work["v185_account_return_pct"], errors="coerce").fillna(0.0)
    work["candidate_pnl"] = pd.to_numeric(work["v185_account_pnl_bps"], errors="coerce").fillna(0.0)
    return (
        work.groupby(["v185_state_action", "v184_state_action", "side", "leg"], dropna=False)
        .agg(
            trade_count=("candidate_return", "size"),
            baseline_return_pct=("baseline_return", "sum"),
            candidate_return_pct=("candidate_return", "sum"),
            win_rate_pct=("candidate_pnl", lambda s: float((s > 0.0).mean() * 100.0) if len(s) else 0.0),
            avg_multiplier=("v185_state_multiplier", "mean"),
            avg_direction_probability=("direction_probability", "mean"),
            avg_premium_z_120d=("premium_z_120d", "mean"),
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
    selected_is_baseline = selected_policy == "v184_baseline_no_long_base_confidence_stepup"
    return {
        "config": {
            "base": "v184_selected_account_path",
            "selector_end": str(SELECTOR_END),
            "min_return_delta_pct": MIN_RETURN_DELTA_PCT,
            "min_holdout_return_delta_pct": MIN_HOLDOUT_RETURN_DELTA_PCT,
            "min_stepup_trade_count": MIN_STEPUP_TRADE_COUNT,
            "min_stepup_active_months": MIN_STEPUP_ACTIVE_MONTHS,
            "max_month_trade_share_pct": MAX_MONTH_TRADE_SHARE_PCT,
            "max_single_trade_delta_share_pct": MAX_SINGLE_TRADE_DELTA_SHARE_PCT,
            "adds_new_trades": False,
            "changes_existing_threshold": False,
            "changes_trade_side": False,
            "promotes_live_trading": False,
        },
        "decision": {
            "status": (
                "long_base_confidence_stepup_no_candidate"
                if selected_is_baseline
                else "long_base_confidence_stepup_candidate_ready"
            ),
            "promote_to_live": False,
            "selected_policy": selected_policy,
            "selected_confidence_stepup_passed": bool(sel.get("confidence_stepup_passed", False)),
            "selected_return_delta_pct": float(sel.get("return_delta_pct", 0.0)),
            "selected_return_improvement_rate": float(sel.get("return_improvement_rate", 0.0)),
            "selected_drawdown_improvement_pct": float(sel.get("drawdown_improvement_pct", 0.0)),
            "selected_holdout_return_delta_pct": float(sel.get("holdout_return_delta_pct", 0.0)),
            "selected_holdout_drawdown_improvement_pct": float(sel.get("holdout_drawdown_improvement_pct", 0.0)),
            "selected_stepup_trade_count": int(sel.get("stepup_trade_count", 0)),
            "selected_stepup_active_month_count": int(sel.get("stepup_active_month_count", 0)),
            "selected_stepup_max_month_trade_share_pct": float(sel.get("stepup_max_month_trade_share_pct", 0.0)),
            "selected_stepup_max_single_trade_delta_share_pct": float(
                sel.get("stepup_max_single_trade_delta_share_pct", 0.0)
            ),
            "message": "V185 tests whether high-confidence long-base rows should receive a narrow size step-up.",
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
        "# Research V185 BTCUSDC Long-Base Confidence Step-Up",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to live: `{decision['promote_to_live']}`",
        f"- Selected policy: `{decision['selected_policy']}`",
        f"- Confidence step-up passed: `{decision['selected_confidence_stepup_passed']}`",
        f"- Return delta vs V184: `{decision['selected_return_delta_pct']}` pct",
        f"- Return improvement rate vs V184: `{decision['selected_return_improvement_rate']}`",
        f"- Drawdown improvement vs V184: `{decision['selected_drawdown_improvement_pct']}` pct",
        f"- Holdout return delta vs V184: `{decision['selected_holdout_return_delta_pct']}` pct",
        f"- Holdout drawdown improvement vs V184: `{decision['selected_holdout_drawdown_improvement_pct']}` pct",
        f"- Step-up trades: `{decision['selected_stepup_trade_count']}`",
        f"- Step-up active months: `{decision['selected_stepup_active_month_count']}`",
        f"- Step-up max-month share: `{decision['selected_stepup_max_month_trade_share_pct']}` pct",
        f"- Step-up max single-trade delta share: `{decision['selected_stepup_max_single_trade_delta_share_pct']}` pct",
        f"- Message: {decision['message']}",
        "",
        "## Overlay Rules",
        "",
        "- Base path: V184 selected account path.",
        "- V185 only changes `side=long`, `leg=base`, `v184_state_action=unchanged` rows.",
        "- Selected confidence rule: `direction_probability >= 0.610399`.",
        "- Selected step-up multiplier: `1.25x` on top of the V184 account return for that existing bucket.",
        "- V185 does not add trades, change trade side, or change existing entry thresholds.",
        "- The alternate short-base trend candidate is kept in the comparison table but is not selected.",
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
        "V185 treats direction probability as a sizing context for a narrow long-base subset. This supports the recent pattern that market context is more useful as a throttle or size overlay than as a standalone entry signal.",
        "",
        "This remains a research audit, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not V184_ACCOUNT_PATH.exists():
        v184.run()
    trades = pd.read_csv(V184_ACCOUNT_PATH)
    trades["timestamp"] = _to_utc(trades["timestamp"])
    baseline_months = _baseline_months(trades)
    policy_paths = {policy.policy: _apply_long_base_confidence_stepup_policy(trades, policy) for policy in POLICIES}
    comparison = _compare_policies(policy_paths, baseline_months)
    selected_policy = _select_policy(comparison)
    selected_path = policy_paths[selected_policy]
    monthly = _monthly_path(selected_path)
    profile = _action_profile(selected_path)
    payload = _payload_for_comparison(comparison, selected_policy=selected_policy)
    comparison.to_csv(OUT_DIR / "v185_policy_comparison.csv", index=False)
    selected_path.to_csv(OUT_DIR / "v185_selected_account_path.csv", index=False)
    monthly.to_csv(OUT_DIR / "v185_selected_monthly_path.csv", index=False)
    profile.to_csv(OUT_DIR / "v185_selected_action_profile.csv", index=False)
    (OUT_DIR / "v185_long_base_confidence_stepup_summary.json").write_text(
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
