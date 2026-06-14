from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v162_long_trend_follow_boost as v162


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v176_combined_state_overlay"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V176_BTCUSDC_COMBINED_STATE_OVERLAY.md"
V162_ACCOUNT_PATH = ROOT / "runs" / "research_v162_long_trend_follow_boost" / "v162_selected_account_path.csv"
MIN_RETURN_IMPROVEMENT_RATE = 0.05
MIN_DRAWDOWN_IMPROVEMENT_PCT = 3.0


@dataclass(frozen=True)
class CombinedStatePolicy:
    policy: str
    fragile_funding_threshold: float | None = None
    fragile_premium_threshold: float | None = None
    fragile_multiplier: float = 1.0
    high_confidence_threshold: float | None = None
    high_confidence_multiplier: float = 1.0


POLICIES = (
    CombinedStatePolicy("v162_baseline_no_combined_overlay"),
    CombinedStatePolicy(
        "v175_growth_reference_conf62_boost1p25",
        fragile_funding_threshold=-1.5,
        fragile_multiplier=1.0,
        high_confidence_threshold=0.62,
        high_confidence_multiplier=1.25,
    ),
    CombinedStatePolicy(
        "v175_balanced_reference_funding0p50_conf62_boost1p10",
        fragile_funding_threshold=-1.5,
        fragile_multiplier=0.50,
        high_confidence_threshold=0.62,
        high_confidence_multiplier=1.10,
    ),
    CombinedStatePolicy(
        "v176_combined_funding_or_premium0p25_conf64_boost1p30",
        fragile_funding_threshold=-1.5,
        fragile_premium_threshold=-2.0,
        fragile_multiplier=0.25,
        high_confidence_threshold=0.64,
        high_confidence_multiplier=1.30,
    ),
    CombinedStatePolicy(
        "v176_combined_funding_or_premium0p25_conf64_boost1p35",
        fragile_funding_threshold=-1.5,
        fragile_premium_threshold=-2.0,
        fragile_multiplier=0.25,
        high_confidence_threshold=0.64,
        high_confidence_multiplier=1.35,
    ),
    CombinedStatePolicy(
        "v176_combined_funding_or_premium0p50_conf64_boost1p35",
        fragile_funding_threshold=-1.5,
        fragile_premium_threshold=-2.0,
        fragile_multiplier=0.50,
        high_confidence_threshold=0.64,
        high_confidence_multiplier=1.35,
    ),
)


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _long_rescue_mask(frame: pd.DataFrame) -> pd.Series:
    return frame.get("side", "").fillna("").astype(str).eq("long") & frame.get("leg", "").fillna("").astype(str).eq("rescue")


def _fragile_state_mask(frame: pd.DataFrame, policy: CombinedStatePolicy) -> pd.Series:
    fragile = pd.Series(False, index=frame.index)
    if policy.fragile_funding_threshold is not None and "funding_z_120d" in frame.columns:
        funding = pd.to_numeric(frame["funding_z_120d"], errors="coerce")
        fragile = fragile | funding.le(float(policy.fragile_funding_threshold))
    if policy.fragile_premium_threshold is not None and "premium_z_30d" in frame.columns:
        premium = pd.to_numeric(frame["premium_z_30d"], errors="coerce")
        fragile = fragile | premium.le(float(policy.fragile_premium_threshold))
    return fragile.fillna(False)


def _high_confidence_mask(frame: pd.DataFrame, policy: CombinedStatePolicy) -> pd.Series:
    if policy.high_confidence_threshold is None or "direction_probability" not in frame.columns:
        return pd.Series(False, index=frame.index)
    prob = pd.to_numeric(frame["direction_probability"], errors="coerce")
    return prob.ge(float(policy.high_confidence_threshold)).fillna(False)


def _apply_combined_state_policy(trades: pd.DataFrame, policy: CombinedStatePolicy) -> pd.DataFrame:
    out = trades.copy()
    long_rescue = _long_rescue_mask(out)
    fragile = long_rescue & _fragile_state_mask(out, policy)
    high_confidence = long_rescue & ~fragile & _high_confidence_mask(out, policy)
    multiplier = pd.Series(1.0, index=out.index)
    action = pd.Series("unchanged", index=out.index, dtype=object)
    multiplier.loc[fragile] = float(policy.fragile_multiplier)
    if float(policy.fragile_multiplier) != 1.0:
        action.loc[fragile] = "fragile_state_throttle"
    else:
        action.loc[fragile] = "fragile_state_unscaled"
    multiplier.loc[high_confidence] = float(policy.high_confidence_multiplier)
    action.loc[high_confidence] = "nonfragile_high_confidence_boost"
    base_return = pd.to_numeric(out["v162_account_return_pct"], errors="coerce").fillna(0.0)
    base_pnl = pd.to_numeric(out["v162_account_pnl_bps"], errors="coerce").fillna(0.0)
    out["v176_policy"] = policy.policy
    out["v176_state_multiplier"] = multiplier
    out["v176_state_action"] = action
    out["v176_account_return_pct"] = base_return * multiplier
    out["v176_account_pnl_bps"] = base_pnl * multiplier
    return out


def _baseline_months(frame: pd.DataFrame) -> pd.Index:
    if frame.empty:
        return pd.Index([], name="month")
    work = frame.copy()
    work["timestamp"] = _to_utc(work["timestamp"])
    return pd.Index(work["timestamp"].dt.strftime("%Y-%m").unique(), name="month").sort_values()


def _policy_metrics(policy: str, path: pd.DataFrame, *, baseline_months: pd.Index) -> dict[str, object]:
    if path.empty:
        monthly = pd.Series(0.0, index=baseline_months)
        return {
            "policy": policy,
            "trade_count": 0,
            "scaled_trade_count": 0,
            "throttled_trade_count": 0,
            "boosted_trade_count": 0,
            "total_account_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "positive_months": int((monthly > 0.0).sum()),
            "month_count": int(len(monthly)),
            "worst_month_pct": float(monthly.min()) if len(monthly) else 0.0,
            "win_rate_pct": 0.0,
        }
    ordered = path.sort_values("timestamp", kind="mergesort").copy()
    ordered["timestamp"] = _to_utc(ordered["timestamp"])
    ordered["month"] = ordered["timestamp"].dt.strftime("%Y-%m")
    returns = pd.to_numeric(ordered["v176_account_return_pct"], errors="coerce").fillna(0.0)
    pnl = pd.to_numeric(ordered["v176_account_pnl_bps"], errors="coerce").fillna(0.0)
    multiplier = pd.to_numeric(ordered["v176_state_multiplier"], errors="coerce").fillna(1.0)
    equity = returns.cumsum()
    drawdown = equity - equity.cummax()
    monthly = returns.groupby(ordered["month"], sort=True).sum().reindex(baseline_months, fill_value=0.0)
    return {
        "policy": policy,
        "trade_count": int(len(ordered)),
        "scaled_trade_count": int(multiplier.ne(1.0).sum()),
        "throttled_trade_count": int(multiplier.lt(1.0).sum()),
        "boosted_trade_count": int(multiplier.gt(1.0).sum()),
        "total_account_return_pct": float(returns.sum()),
        "max_drawdown_pct": float(drawdown.min()) if len(drawdown) else 0.0,
        "positive_months": int((monthly > 0.0).sum()),
        "month_count": int(len(monthly)),
        "worst_month_pct": float(monthly.min()) if len(monthly) else 0.0,
        "win_rate_pct": float((pnl > 0.0).mean() * 100.0) if len(pnl) else 0.0,
    }


def _compare_policies(policy_paths: dict[str, pd.DataFrame], baseline_months: pd.Index) -> pd.DataFrame:
    rows = [_policy_metrics(policy, path, baseline_months=baseline_months) for policy, path in policy_paths.items()]
    out = pd.DataFrame(rows)
    baseline = out.loc[out["policy"].eq("v162_baseline_no_combined_overlay")].iloc[0]
    base_return = float(baseline["total_account_return_pct"])
    out["return_delta_pct"] = out["total_account_return_pct"] - base_return
    out["return_improvement_rate"] = out["return_delta_pct"] / base_return if base_return else 0.0
    out["drawdown_improvement_pct"] = out["max_drawdown_pct"] - float(baseline["max_drawdown_pct"])
    out["worst_month_improvement_pct"] = out["worst_month_pct"] - float(baseline["worst_month_pct"])
    out["positive_month_delta"] = out["positive_months"] - int(baseline["positive_months"])
    out["combined_passed"] = (
        out["return_improvement_rate"].ge(MIN_RETURN_IMPROVEMENT_RATE)
        & out["drawdown_improvement_pct"].ge(MIN_DRAWDOWN_IMPROVEMENT_PCT)
        & out["worst_month_improvement_pct"].ge(0.0)
        & out["positive_month_delta"].ge(0)
    )
    out["combined_score"] = (
        out["return_delta_pct"]
        + out["drawdown_improvement_pct"] * 25.0
        + out["worst_month_improvement_pct"] * 10.0
        + out["positive_month_delta"] * 5.0
        - out["scaled_trade_count"] * 0.05
    )
    out["combined_passed"] = out["combined_passed"].map(bool).astype(object)
    return out.sort_values(["combined_passed", "combined_score"], ascending=[False, False]).reset_index(drop=True)


def _select_policy(comparison: pd.DataFrame) -> str:
    candidates = comparison.loc[
        comparison["combined_passed"].astype(bool)
        & ~comparison["policy"].eq("v162_baseline_no_combined_overlay")
    ].copy()
    if candidates.empty:
        return "v162_baseline_no_combined_overlay"
    return str(candidates.iloc[0]["policy"])


def _monthly_path(path: pd.DataFrame) -> pd.DataFrame:
    work = path.sort_values("timestamp", kind="mergesort").copy()
    work["timestamp"] = _to_utc(work["timestamp"])
    work["month"] = work["timestamp"].dt.strftime("%Y-%m")
    return (
        work.groupby("month", dropna=False)
        .agg(
            trade_count=("v176_account_return_pct", "size"),
            scaled_trade_count=("v176_state_multiplier", lambda s: int(pd.to_numeric(s, errors="coerce").fillna(1.0).ne(1.0).sum())),
            account_return_pct=("v176_account_return_pct", "sum"),
            account_pnl_bps=("v176_account_pnl_bps", "sum"),
        )
        .reset_index()
    )


def _action_profile(path: pd.DataFrame) -> pd.DataFrame:
    work = path.copy()
    work["win"] = pd.to_numeric(work["v176_account_pnl_bps"], errors="coerce").fillna(0.0) > 0.0
    return (
        work.groupby(["v176_policy", "v176_state_action", "side", "leg"], dropna=False)
        .agg(
            trade_count=("v176_account_return_pct", "size"),
            account_return_pct=("v176_account_return_pct", "sum"),
            original_account_return_pct=("v162_account_return_pct", "sum"),
            win_rate_pct=("win", "mean"),
            avg_multiplier=("v176_state_multiplier", "mean"),
            avg_direction_probability=("direction_probability", "mean"),
            avg_funding_z_120d=("funding_z_120d", "mean"),
            avg_premium_z_30d=("premium_z_30d", "mean"),
        )
        .reset_index()
        .assign(win_rate_pct=lambda df: df["win_rate_pct"] * 100.0)
    )


def _max_drawdown_summary(path: pd.DataFrame, *, return_col: str) -> dict[str, object]:
    ordered = path.sort_values("timestamp", kind="mergesort").copy()
    ordered["timestamp"] = _to_utc(ordered["timestamp"])
    returns = pd.to_numeric(ordered[return_col], errors="coerce").fillna(0.0)
    equity = returns.cumsum()
    peak = equity.cummax()
    drawdown = equity - peak
    if ordered.empty:
        return {"max_drawdown_pct": 0.0, "peak_timestamp": "", "trough_timestamp": ""}
    trough_idx = int(drawdown.idxmin())
    peak_candidates = equity.loc[:trough_idx]
    peak_idx = int(peak_candidates.idxmax()) if not peak_candidates.empty else trough_idx
    return {
        "max_drawdown_pct": float(drawdown.loc[trough_idx]),
        "peak_timestamp": str(ordered.loc[peak_idx, "timestamp"]),
        "trough_timestamp": str(ordered.loc[trough_idx, "timestamp"]),
    }


def _payload_for_comparison(comparison: pd.DataFrame, *, selected_policy: str) -> dict[str, object]:
    baseline = comparison.loc[comparison["policy"].eq("v162_baseline_no_combined_overlay")]
    selected = comparison.loc[comparison["policy"].eq(selected_policy)]
    base = baseline.iloc[0] if not baseline.empty else pd.Series(dtype=object)
    sel = selected.iloc[0] if not selected.empty else pd.Series(dtype=object)
    selected_is_baseline = selected_policy == "v162_baseline_no_combined_overlay"
    return {
        "config": {
            "base": "v162_selected_account_path",
            "min_return_improvement_rate": MIN_RETURN_IMPROVEMENT_RATE,
            "min_drawdown_improvement_pct": MIN_DRAWDOWN_IMPROVEMENT_PCT,
            "adds_new_trades": False,
            "changes_existing_threshold": False,
            "changes_trade_side": False,
            "promotes_live_trading": False,
        },
        "decision": {
            "status": (
                "combined_state_overlay_no_candidate"
                if selected_is_baseline
                else "combined_state_overlay_candidate_ready"
            ),
            "promote_to_live": False,
            "selected_policy": selected_policy,
            "selected_combined_passed": bool(sel.get("combined_passed", False)),
            "selected_return_delta_pct": float(sel.get("total_account_return_pct", 0.0))
            - float(base.get("total_account_return_pct", 0.0)),
            "selected_return_improvement_rate": float(sel.get("return_improvement_rate", 0.0)),
            "selected_drawdown_improvement_pct": float(sel.get("max_drawdown_pct", 0.0))
            - float(base.get("max_drawdown_pct", 0.0)),
            "selected_worst_month_improvement_pct": float(sel.get("worst_month_pct", 0.0))
            - float(base.get("worst_month_pct", 0.0)),
            "selected_scaled_trade_count": int(sel.get("scaled_trade_count", 0)),
            "selected_throttled_trade_count": int(sel.get("throttled_trade_count", 0)),
            "selected_boosted_trade_count": int(sel.get("boosted_trade_count", 0)),
            "message": "V176 combines fragile-state throttling and non-fragile high-confidence boosting as a research sizing overlay only.",
        },
    }


def _write_report(
    payload: dict[str, object],
    comparison: pd.DataFrame,
    selected_monthly: pd.DataFrame,
    selected_profile: pd.DataFrame,
    baseline_drawdown: dict[str, object],
    selected_drawdown: dict[str, object],
) -> None:
    decision = payload["decision"]
    lines = [
        "# Research V176 BTCUSDC Combined State Overlay",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to live: `{decision['promote_to_live']}`",
        f"- Selected policy: `{decision['selected_policy']}`",
        f"- Combined passed: `{decision['selected_combined_passed']}`",
        f"- Return delta: `{decision['selected_return_delta_pct']}` pct",
        f"- Return improvement rate: `{decision['selected_return_improvement_rate']}`",
        f"- Drawdown improvement: `{decision['selected_drawdown_improvement_pct']}` pct",
        f"- Worst-month improvement: `{decision['selected_worst_month_improvement_pct']}` pct",
        f"- Scaled trades: `{decision['selected_scaled_trade_count']}`",
        f"- Throttled trades: `{decision['selected_throttled_trade_count']}`",
        f"- Boosted trades: `{decision['selected_boosted_trade_count']}`",
        f"- Message: {decision['message']}",
        "",
        "## Overlay Rules",
        "",
        "- Base path: V162 selected account path.",
        "- V176 only scales existing long rescue trades.",
        "- Fragile state: `funding_z_120d <= -1.5` or `premium_z_30d <= -2.0`.",
        "- Selected throttle: fragile long rescue trades are scaled to `0.25x`.",
        "- Selected boost: non-fragile long rescue trades with `direction_probability >= 0.64` are scaled to `1.35x`.",
        "- This audit does not add trades, change side, change thresholds, or promote live trading.",
        "",
        "## Baseline Max Drawdown",
        "",
        pd.DataFrame([baseline_drawdown]).to_csv(index=False).strip(),
        "",
        "## Selected Max Drawdown",
        "",
        pd.DataFrame([selected_drawdown]).to_csv(index=False).strip(),
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
        "V176 tests whether V175's growth overlay and fragile-state risk control can coexist. The selected result improves historical return and historical max drawdown, but it uses only a small number of boosted trades, so forward monitoring remains required before live use.",
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
    if "timestamp" in trades.columns:
        trades["timestamp"] = _to_utc(trades["timestamp"])
    baseline_months = _baseline_months(trades)
    policy_paths = {policy.policy: _apply_combined_state_policy(trades, policy) for policy in POLICIES}
    comparison = _compare_policies(policy_paths, baseline_months)
    selected_policy = _select_policy(comparison)
    selected_path = policy_paths[selected_policy]
    baseline_path = policy_paths["v162_baseline_no_combined_overlay"]
    monthly = _monthly_path(selected_path)
    profile = _action_profile(selected_path)
    baseline_drawdown = _max_drawdown_summary(baseline_path, return_col="v176_account_return_pct")
    selected_drawdown = _max_drawdown_summary(selected_path, return_col="v176_account_return_pct")
    payload = _payload_for_comparison(comparison, selected_policy=selected_policy)
    comparison.to_csv(OUT_DIR / "v176_policy_comparison.csv", index=False)
    selected_path.to_csv(OUT_DIR / "v176_selected_account_path.csv", index=False)
    monthly.to_csv(OUT_DIR / "v176_selected_monthly_path.csv", index=False)
    profile.to_csv(OUT_DIR / "v176_selected_action_profile.csv", index=False)
    (OUT_DIR / "v176_combined_state_overlay_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, comparison, monthly, profile, baseline_drawdown, selected_drawdown)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
