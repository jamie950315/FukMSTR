from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v192_long_base_low_probz_throttle as v192


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v193_long_base_top5_premium6h_throttle"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V193_BTCUSDC_LONG_BASE_TOP5_PREMIUM6H_THROTTLE.md"
V192_ACCOUNT_PATH = ROOT / "runs" / "research_v192_long_base_low_probz_throttle" / "v192_selected_account_path.csv"
SELECTOR_END = pd.Timestamp("2026-01-01T00:00:00Z")
EPSILON = 1e-9
MIN_RETURN_DELTA_PCT = 10.0
MIN_HOLDOUT_RETURN_DELTA_PCT = 5.0
MIN_THROTTLE_TRADE_COUNT = 15
MIN_THROTTLE_ACTIVE_MONTHS = 8
MAX_MONTH_TRADE_SHARE_PCT = 35.0
MAX_SINGLE_TRADE_DELTA_SHARE_PCT = 35.0


@dataclass(frozen=True)
class LongBaseTop5Premium6hThrottlePolicy:
    policy: str
    min_premium_close_bps_6h: float | None = None
    target_indicator_key: str = "v125_top5_lb14_strict"
    target_side: str = "long"
    target_leg: str = "base"
    require_v188_action: str = "unchanged"
    require_v189_action: str = "unchanged"
    require_v190_action: str = "unchanged"
    require_v191_action: str = "unchanged"
    require_v192_action: str = "unchanged"
    throttle_multiplier: float = 1.0
    throttle_action: str = "long_base_top5_premium6h_throttle"


POLICIES = (
    LongBaseTop5Premium6hThrottlePolicy(
        "v192_baseline_no_long_base_top5_premium6h_throttle",
        throttle_multiplier=1.0,
        throttle_action="unchanged",
    ),
    LongBaseTop5Premium6hThrottlePolicy(
        "v193_long_base_top5_premium6h_ge_neg4p576517_throttle0p00",
        min_premium_close_bps_6h=-4.576517,
        throttle_multiplier=0.0,
    ),
    LongBaseTop5Premium6hThrottlePolicy(
        "v193_long_base_top5_premium6h_ge_neg4p576517_throttle0p25",
        min_premium_close_bps_6h=-4.576517,
        throttle_multiplier=0.25,
    ),
    LongBaseTop5Premium6hThrottlePolicy(
        "v193_long_base_top5_premium6h_ge_neg4p576517_throttle0p50",
        min_premium_close_bps_6h=-4.576517,
        throttle_multiplier=0.5,
    ),
)


def _to_utc(series: pd.Series) -> pd.Series:
    return v192._to_utc(series)


def _baseline_months(frame: pd.DataFrame) -> pd.Index:
    return v192._baseline_months(frame)


def _max_drawdown(returns: pd.Series) -> float:
    return v192._max_drawdown(returns)


def _throttle_mask(frame: pd.DataFrame, policy: LongBaseTop5Premium6hThrottlePolicy) -> pd.Series:
    if float(policy.throttle_multiplier) == 1.0:
        return pd.Series(False, index=frame.index)
    mask = (
        frame.get("indicator_key", "").fillna("").astype(str).eq(policy.target_indicator_key)
        & frame.get("side", "").fillna("").astype(str).eq(policy.target_side)
        & frame.get("leg", "").fillna("").astype(str).eq(policy.target_leg)
        & frame.get("v188_state_action", "").fillna("").astype(str).eq(policy.require_v188_action)
        & frame.get("v189_state_action", "").fillna("").astype(str).eq(policy.require_v189_action)
        & frame.get("v190_state_action", "").fillna("").astype(str).eq(policy.require_v190_action)
        & frame.get("v191_state_action", "").fillna("").astype(str).eq(policy.require_v191_action)
        & frame.get("v192_state_action", "").fillna("").astype(str).eq(policy.require_v192_action)
    )
    if policy.min_premium_close_bps_6h is not None:
        premium_6h = pd.to_numeric(frame.get("premium_close_bps_6h", pd.Series(index=frame.index)), errors="coerce")
        mask &= premium_6h.ge(float(policy.min_premium_close_bps_6h))
    return mask.fillna(False)


def _apply_long_base_top5_premium6h_throttle_policy(
    trades: pd.DataFrame,
    policy: LongBaseTop5Premium6hThrottlePolicy,
) -> pd.DataFrame:
    out = trades.copy()
    throttled = _throttle_mask(out, policy)
    multiplier = pd.Series(1.0, index=out.index)
    action = pd.Series("unchanged", index=out.index, dtype=object)
    multiplier.loc[throttled] = float(policy.throttle_multiplier)
    action.loc[throttled] = policy.throttle_action
    base_return = pd.to_numeric(out["v192_account_return_pct"], errors="coerce").fillna(0.0)
    base_pnl = pd.to_numeric(out["v192_account_pnl_bps"], errors="coerce").fillna(0.0)
    out["v193_policy"] = policy.policy
    out["v193_state_multiplier"] = multiplier
    out["v193_state_action"] = action
    out["v193_account_return_pct"] = base_return * multiplier
    out["v193_account_pnl_bps"] = base_pnl * multiplier
    return out


def _month_concentration(path: pd.DataFrame) -> tuple[int, float]:
    work = path.loc[pd.to_numeric(path["v193_state_multiplier"], errors="coerce").fillna(1.0).lt(1.0)].copy()
    if work.empty:
        return 0, 0.0
    work["timestamp"] = _to_utc(work["timestamp"])
    month_counts = work.groupby(work["timestamp"].dt.strftime("%Y-%m")).size()
    return int(month_counts.size), float(month_counts.max() / len(work) * 100.0)


def _single_trade_delta_share(path: pd.DataFrame) -> float:
    multiplier = pd.to_numeric(path["v193_state_multiplier"], errors="coerce").fillna(1.0)
    throttled = multiplier.lt(1.0)
    if not throttled.any():
        return 0.0
    candidate_return = pd.to_numeric(path["v193_account_return_pct"], errors="coerce").fillna(0.0)
    if "v192_account_return_pct" in path.columns:
        base_return = pd.to_numeric(path["v192_account_return_pct"], errors="coerce").fillna(0.0)
    else:
        base_return = candidate_return
    delta = (candidate_return.loc[throttled] - base_return.loc[throttled]).abs()
    total = float(delta.sum())
    return float(delta.max() / total * 100.0) if total else 0.0


def _policy_metrics(policy: str, path: pd.DataFrame, *, baseline_months: pd.Index) -> dict[str, object]:
    if path.empty:
        monthly = pd.Series(0.0, index=baseline_months)
        holdout_monthly = monthly[monthly.index >= SELECTOR_END.strftime("%Y-%m")]
        return {
            "policy": policy,
            "trade_count": 0,
            "throttle_trade_count": 0,
            "throttle_active_month_count": 0,
            "throttle_max_month_trade_share_pct": 0.0,
            "throttle_max_single_trade_delta_share_pct": 0.0,
            "total_account_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "positive_months": int((monthly > 0.0).sum()),
            "month_count": int(len(monthly)),
            "worst_month_pct": float(monthly.min()) if len(monthly) else 0.0,
            "holdout_return_pct": 0.0,
            "holdout_max_drawdown_pct": 0.0,
            "holdout_positive_months": int((holdout_monthly > 0.0).sum()),
            "holdout_month_count": int(len(holdout_monthly)),
        }
    ordered = path.sort_values("timestamp", kind="mergesort").copy()
    ordered["timestamp"] = _to_utc(ordered["timestamp"])
    ordered["month"] = ordered["timestamp"].dt.strftime("%Y-%m")
    returns = pd.to_numeric(ordered["v193_account_return_pct"], errors="coerce").fillna(0.0)
    monthly = returns.groupby(ordered["month"], sort=True).sum().reindex(baseline_months, fill_value=0.0)
    holdout_mask = ordered["timestamp"].ge(SELECTOR_END)
    holdout_returns = returns.loc[holdout_mask]
    holdout_monthly = monthly[monthly.index >= SELECTOR_END.strftime("%Y-%m")]
    throttled = pd.to_numeric(ordered["v193_state_multiplier"], errors="coerce").fillna(1.0).lt(1.0)
    active_months, max_share = _month_concentration(ordered)
    return {
        "policy": policy,
        "trade_count": int(len(ordered)),
        "throttle_trade_count": int(throttled.sum()),
        "throttle_active_month_count": active_months,
        "throttle_max_month_trade_share_pct": max_share,
        "throttle_max_single_trade_delta_share_pct": _single_trade_delta_share(ordered),
        "total_account_return_pct": float(returns.sum()),
        "max_drawdown_pct": _max_drawdown(returns),
        "positive_months": int((monthly > 0.0).sum()),
        "month_count": int(len(monthly)),
        "worst_month_pct": float(monthly.min()) if len(monthly) else 0.0,
        "holdout_return_pct": float(holdout_returns.sum()),
        "holdout_max_drawdown_pct": _max_drawdown(holdout_returns),
        "holdout_positive_months": int((holdout_monthly > 0.0).sum()),
        "holdout_month_count": int(len(holdout_monthly)),
    }


def _compare_policies(policy_paths: dict[str, pd.DataFrame], baseline_months: pd.Index) -> pd.DataFrame:
    rows = [_policy_metrics(policy, path, baseline_months=baseline_months) for policy, path in policy_paths.items()]
    out = pd.DataFrame(rows)
    baseline = out.loc[out["policy"].eq("v192_baseline_no_long_base_top5_premium6h_throttle")].iloc[0]
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
    out["holdout_positive_month_delta"] = out["holdout_positive_months"] - int(baseline["holdout_positive_months"])
    out["top5_premium6h_throttle_passed"] = (
        out["return_delta_pct"].ge(MIN_RETURN_DELTA_PCT)
        & out["holdout_return_delta_pct"].ge(MIN_HOLDOUT_RETURN_DELTA_PCT)
        & out["drawdown_improvement_pct"].ge(-EPSILON)
        & out["holdout_drawdown_improvement_pct"].ge(-EPSILON)
        & out["worst_month_improvement_pct"].ge(-EPSILON)
        & out["positive_month_delta"].ge(0)
        & out["holdout_positive_month_delta"].ge(0)
        & out["throttle_trade_count"].ge(MIN_THROTTLE_TRADE_COUNT)
        & out["throttle_active_month_count"].ge(MIN_THROTTLE_ACTIVE_MONTHS)
        & out["throttle_max_month_trade_share_pct"].le(MAX_MONTH_TRADE_SHARE_PCT)
        & out["throttle_max_single_trade_delta_share_pct"].le(MAX_SINGLE_TRADE_DELTA_SHARE_PCT)
    )
    out["top5_premium6h_throttle_score"] = (
        out["return_delta_pct"]
        + out["holdout_return_delta_pct"] * 1.5
        + out["drawdown_improvement_pct"] * 20.0
        + (MAX_MONTH_TRADE_SHARE_PCT - out["throttle_max_month_trade_share_pct"]).clip(lower=0.0)
        + (MAX_SINGLE_TRADE_DELTA_SHARE_PCT - out["throttle_max_single_trade_delta_share_pct"]).clip(lower=0.0) * 0.5
        - out["throttle_trade_count"] * 0.05
    )
    out["top5_premium6h_throttle_passed"] = out["top5_premium6h_throttle_passed"].map(bool).astype(object)
    return out.sort_values(
        ["top5_premium6h_throttle_passed", "top5_premium6h_throttle_score"],
        ascending=[False, False],
    ).reset_index(drop=True)


def _select_policy(comparison: pd.DataFrame) -> str:
    candidates = comparison.loc[
        comparison["top5_premium6h_throttle_passed"].astype(bool)
        & ~comparison["policy"].eq("v192_baseline_no_long_base_top5_premium6h_throttle")
    ].copy()
    if candidates.empty:
        return "v192_baseline_no_long_base_top5_premium6h_throttle"
    return str(candidates.iloc[0]["policy"])


def _monthly_path(path: pd.DataFrame) -> pd.DataFrame:
    work = path.sort_values("timestamp", kind="mergesort").copy()
    work["timestamp"] = _to_utc(work["timestamp"])
    work["month"] = work["timestamp"].dt.strftime("%Y-%m")
    work["baseline_return"] = pd.to_numeric(work["v192_account_return_pct"], errors="coerce").fillna(0.0)
    work["candidate_return"] = pd.to_numeric(work["v193_account_return_pct"], errors="coerce").fillna(0.0)
    work["throttled"] = pd.to_numeric(work["v193_state_multiplier"], errors="coerce").fillna(1.0).lt(1.0)
    return (
        work.groupby("month", dropna=False)
        .agg(
            trade_count=("candidate_return", "size"),
            throttle_trade_count=("throttled", "sum"),
            baseline_return_pct=("baseline_return", "sum"),
            candidate_return_pct=("candidate_return", "sum"),
        )
        .reset_index()
        .assign(return_delta_pct=lambda df: df["candidate_return_pct"] - df["baseline_return_pct"])
    )


def _action_profile(path: pd.DataFrame) -> pd.DataFrame:
    work = path.copy()
    work["baseline_return"] = pd.to_numeric(work["v192_account_return_pct"], errors="coerce").fillna(0.0)
    work["candidate_return"] = pd.to_numeric(work["v193_account_return_pct"], errors="coerce").fillna(0.0)
    work["candidate_pnl"] = pd.to_numeric(work["v193_account_pnl_bps"], errors="coerce").fillna(0.0)
    return (
        work.groupby(
            [
                "v193_state_action",
                "v192_state_action",
                "v191_state_action",
                "v190_state_action",
                "v189_state_action",
                "v188_state_action",
                "indicator_key",
                "side",
                "leg",
            ],
            dropna=False,
        )
        .agg(
            trade_count=("candidate_return", "size"),
            baseline_return_pct=("baseline_return", "sum"),
            candidate_return_pct=("candidate_return", "sum"),
            win_rate_pct=("candidate_pnl", lambda s: float((s > 0.0).mean() * 100.0) if len(s) else 0.0),
            avg_multiplier=("v193_state_multiplier", "mean"),
            avg_premium_close_bps_6h=("premium_close_bps_6h", "mean"),
            avg_prob_z_7d=("prob_z_7d", "mean"),
            avg_direction_probability=("direction_probability", "mean"),
        )
        .reset_index()
        .assign(return_delta_pct=lambda df: df["candidate_return_pct"] - df["baseline_return_pct"])
    )


def _iteration_metrics_table(comparison: pd.DataFrame, *, selected_policy: str) -> list[dict[str, object]]:
    baseline = comparison.loc[comparison["policy"].eq("v192_baseline_no_long_base_top5_premium6h_throttle")].iloc[0]
    selected = comparison.loc[comparison["policy"].eq(selected_policy)].iloc[0]
    rows = []
    for version, row, improvement in (
        ("V192", baseline, None),
        ("V193", selected, float(selected["return_delta_pct"])),
    ):
        rows.append(
            {
                "version": version,
                "account_return_pct": float(row["total_account_return_pct"]),
                "improvement_pct": "-" if improvement is None else improvement,
                "max_drawdown_pct": float(row["max_drawdown_pct"]),
                "positive_months": f"{int(row['positive_months'])}/{int(row['month_count'])}",
                "holdout_return_pct": float(row["holdout_return_pct"]),
                "holdout_months": f"{int(row['holdout_positive_months'])}/{int(row['holdout_month_count'])}",
            }
        )
    return rows


def _payload_for_comparison(comparison: pd.DataFrame, *, selected_policy: str) -> dict[str, object]:
    selected = comparison.loc[comparison["policy"].eq(selected_policy)]
    sel = selected.iloc[0] if not selected.empty else pd.Series(dtype=object)
    selected_is_baseline = selected_policy == "v192_baseline_no_long_base_top5_premium6h_throttle"
    return {
        "config": {
            "base": "v192_selected_account_path",
            "selector_end": str(SELECTOR_END),
            "min_return_delta_pct": MIN_RETURN_DELTA_PCT,
            "min_holdout_return_delta_pct": MIN_HOLDOUT_RETURN_DELTA_PCT,
            "min_throttle_trade_count": MIN_THROTTLE_TRADE_COUNT,
            "min_throttle_active_months": MIN_THROTTLE_ACTIVE_MONTHS,
            "max_month_trade_share_pct": MAX_MONTH_TRADE_SHARE_PCT,
            "max_single_trade_delta_share_pct": MAX_SINGLE_TRADE_DELTA_SHARE_PCT,
            "adds_new_trades": False,
            "changes_existing_threshold": False,
            "changes_trade_side": False,
            "promotes_live_trading": False,
            "requires_iteration_metrics_table": True,
        },
        "decision": {
            "status": (
                "long_base_top5_premium6h_throttle_no_candidate"
                if selected_is_baseline
                else "long_base_top5_premium6h_throttle_candidate_ready"
            ),
            "promote_to_live": False,
            "selected_policy": selected_policy,
            "selected_top5_premium6h_throttle_passed": bool(sel.get("top5_premium6h_throttle_passed", False)),
            "selected_return_delta_pct": float(sel.get("return_delta_pct", 0.0)),
            "selected_return_improvement_rate": float(sel.get("return_improvement_rate", 0.0)),
            "selected_drawdown_improvement_pct": float(sel.get("drawdown_improvement_pct", 0.0)),
            "selected_holdout_return_delta_pct": float(sel.get("holdout_return_delta_pct", 0.0)),
            "selected_holdout_drawdown_improvement_pct": float(sel.get("holdout_drawdown_improvement_pct", 0.0)),
            "selected_throttle_trade_count": int(sel.get("throttle_trade_count", 0)),
            "selected_throttle_active_month_count": int(sel.get("throttle_active_month_count", 0)),
            "selected_throttle_max_month_trade_share_pct": float(sel.get("throttle_max_month_trade_share_pct", 0.0)),
            "selected_throttle_max_single_trade_delta_share_pct": float(
                sel.get("throttle_max_single_trade_delta_share_pct", 0.0)
            ),
            "message": (
                "V193 removes exposure in an independent top5 long-base premium-6h bucket and avoids modifying "
                "rows already changed by V188 through V192."
            ),
        },
        "iteration_metrics_table": _iteration_metrics_table(comparison, selected_policy=selected_policy),
    }


def _metrics_table_markdown(rows: list[dict[str, object]]) -> str:
    lines = [
        "| Metric | V192 | V193 |",
        "|---|---:|---:|",
        f"| Account return estimate | {rows[0]['account_return_pct']:.2f}% | {rows[1]['account_return_pct']:.2f}% |",
        f"| Improvement | - | +{rows[1]['improvement_pct']:.2f} percentage points |",
        f"| Max drawdown | {rows[0]['max_drawdown_pct']:.2f}% | {rows[1]['max_drawdown_pct']:.2f}% |",
        f"| Positive months | {rows[0]['positive_months']} | {rows[1]['positive_months']} |",
        f"| Holdout return | {rows[0]['holdout_return_pct']:.2f}% | {rows[1]['holdout_return_pct']:.2f}% |",
        f"| Holdout months | {rows[0]['holdout_months']} | {rows[1]['holdout_months']} |",
    ]
    return "\n".join(lines)


def _write_report(
    payload: dict[str, object],
    comparison: pd.DataFrame,
    selected_monthly: pd.DataFrame,
    selected_profile: pd.DataFrame,
) -> None:
    decision = payload["decision"]
    lines = [
        "# Research V193 BTCUSDC Long-Base Top5 Premium6h Throttle",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to live: `{decision['promote_to_live']}`",
        f"- Selected policy: `{decision['selected_policy']}`",
        f"- Top5 premium6h throttle passed: `{decision['selected_top5_premium6h_throttle_passed']}`",
        f"- Return delta vs V192: `{decision['selected_return_delta_pct']}` pct",
        f"- Return improvement rate vs V192: `{decision['selected_return_improvement_rate']}`",
        f"- Drawdown improvement vs V192: `{decision['selected_drawdown_improvement_pct']}` pct",
        f"- Holdout return delta vs V192: `{decision['selected_holdout_return_delta_pct']}` pct",
        f"- Holdout drawdown improvement vs V192: `{decision['selected_holdout_drawdown_improvement_pct']}` pct",
        f"- Throttle trades: `{decision['selected_throttle_trade_count']}`",
        f"- Throttle active months: `{decision['selected_throttle_active_month_count']}`",
        f"- Throttle max-month share: `{decision['selected_throttle_max_month_trade_share_pct']}` pct",
        f"- Throttle max single-trade delta share: `{decision['selected_throttle_max_single_trade_delta_share_pct']}` pct",
        f"- Message: {decision['message']}",
        "",
        "## Iteration Metrics",
        "",
        _metrics_table_markdown(payload["iteration_metrics_table"]),
        "",
        "## Overlay Rules",
        "",
        "- Base path: V192 selected account path.",
        "- V193 only changes `indicator_key=v125_top5_lb14_strict`, `side=long`, `leg=base`, `v188_state_action=unchanged`, `v189_state_action=unchanged`, `v190_state_action=unchanged`, `v191_state_action=unchanged`, `v192_state_action=unchanged` rows.",
        "- Selected 6-hour premium rule: `premium_close_bps_6h >= -4.576517`.",
        "- Selected throttle multiplier: `0.00x` on top of the V192 account return for that existing bucket.",
        "- V193 does not add trades, change trade side, or change existing entry thresholds.",
        "- V193 deliberately avoids rows already modified by V188, V189, V190, V191, or V192.",
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
        "V193 treats insufficiently negative 6-hour premium as a risk context for a remaining top5 long-base bucket. It removes size only; it is not a new entry or exit signal.",
        "",
        "This remains a research audit, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not V192_ACCOUNT_PATH.exists():
        v192.run()
    trades = pd.read_csv(V192_ACCOUNT_PATH)
    trades["timestamp"] = _to_utc(trades["timestamp"])
    baseline_months = _baseline_months(trades)
    policy_paths = {policy.policy: _apply_long_base_top5_premium6h_throttle_policy(trades, policy) for policy in POLICIES}
    comparison = _compare_policies(policy_paths, baseline_months)
    selected_policy = _select_policy(comparison)
    selected_path = policy_paths[selected_policy]
    monthly = _monthly_path(selected_path)
    profile = _action_profile(selected_path)
    payload = _payload_for_comparison(comparison, selected_policy=selected_policy)
    comparison.to_csv(OUT_DIR / "v193_policy_comparison.csv", index=False)
    selected_path.to_csv(OUT_DIR / "v193_selected_account_path.csv", index=False)
    monthly.to_csv(OUT_DIR / "v193_selected_monthly_path.csv", index=False)
    profile.to_csv(OUT_DIR / "v193_selected_action_profile.csv", index=False)
    (OUT_DIR / "v193_long_base_top5_premium6h_throttle_summary.json").write_text(
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
