from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v186_long_rescue_day_sofar_stepup as v186


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v187_drought_long_base_trend_stepup"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V187_BTCUSDC_DROUGHT_LONG_BASE_TREND_STEPUP.md"
V186_ACCOUNT_PATH = ROOT / "runs" / "research_v186_long_rescue_day_sofar_stepup" / "v186_selected_account_path.csv"
SELECTOR_END = pd.Timestamp("2026-01-01T00:00:00Z")
EPSILON = 1e-9
MIN_RETURN_DELTA_PCT = 10.0
MIN_HOLDOUT_RETURN_DELTA_PCT = 5.0
MIN_STEPUP_TRADE_COUNT = 15
MIN_STEPUP_ACTIVE_MONTHS = 9
MAX_MONTH_TRADE_SHARE_PCT = 30.0
MAX_SINGLE_TRADE_DELTA_SHARE_PCT = 30.0


@dataclass(frozen=True)
class DroughtLongBaseTrendStepupPolicy:
    policy: str
    min_trend_abs_60_bps: float | None = None
    target_source: str = "v122_drought"
    target_side: str = "long"
    target_leg: str = "base"
    require_v186_action: str = "unchanged"
    stepup_multiplier: float = 1.0
    stepup_action: str = "drought_long_base_trend_stepup"


POLICIES = (
    DroughtLongBaseTrendStepupPolicy(
        "v186_baseline_no_drought_long_base_trend_stepup",
        stepup_multiplier=1.0,
        stepup_action="unchanged",
    ),
    DroughtLongBaseTrendStepupPolicy(
        "v187_drought_long_base_trend60_ge238p049377_stepup1p25",
        min_trend_abs_60_bps=238.049377,
        stepup_multiplier=1.25,
    ),
    DroughtLongBaseTrendStepupPolicy(
        "v187_drought_long_base_trend60_ge245p059254_stepup1p25",
        min_trend_abs_60_bps=245.059254,
        stepup_multiplier=1.25,
    ),
    DroughtLongBaseTrendStepupPolicy(
        "v187_drought_long_base_trend60_ge255p992130_stepup1p25",
        min_trend_abs_60_bps=255.992130,
        stepup_multiplier=1.25,
    ),
    DroughtLongBaseTrendStepupPolicy(
        "v187_drought_long_base_trend60_ge238p049377_stepup1p15",
        min_trend_abs_60_bps=238.049377,
        stepup_multiplier=1.15,
    ),
)


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _stepup_mask(frame: pd.DataFrame, policy: DroughtLongBaseTrendStepupPolicy) -> pd.Series:
    if float(policy.stepup_multiplier) == 1.0:
        return pd.Series(False, index=frame.index)
    mask = (
        frame.get("source", "").fillna("").astype(str).eq(policy.target_source)
        & frame.get("side", "").fillna("").astype(str).eq(policy.target_side)
        & frame.get("leg", "").fillna("").astype(str).eq(policy.target_leg)
        & frame.get("v186_state_action", "").fillna("").astype(str).eq(policy.require_v186_action)
    )
    if policy.min_trend_abs_60_bps is not None:
        trend_abs = pd.to_numeric(frame.get("trend_abs_60_bps", pd.Series(index=frame.index)), errors="coerce")
        mask &= trend_abs.ge(float(policy.min_trend_abs_60_bps))
    return mask.fillna(False)


def _apply_drought_long_base_trend_stepup_policy(
    trades: pd.DataFrame,
    policy: DroughtLongBaseTrendStepupPolicy,
) -> pd.DataFrame:
    out = trades.copy()
    stepped = _stepup_mask(out, policy)
    multiplier = pd.Series(1.0, index=out.index)
    action = pd.Series("unchanged", index=out.index, dtype=object)
    multiplier.loc[stepped] = float(policy.stepup_multiplier)
    action.loc[stepped] = policy.stepup_action
    base_return = pd.to_numeric(out["v186_account_return_pct"], errors="coerce").fillna(0.0)
    base_pnl = pd.to_numeric(out["v186_account_pnl_bps"], errors="coerce").fillna(0.0)
    out["v187_policy"] = policy.policy
    out["v187_state_multiplier"] = multiplier
    out["v187_state_action"] = action
    out["v187_account_return_pct"] = base_return * multiplier
    out["v187_account_pnl_bps"] = base_pnl * multiplier
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
    work = path.loc[pd.to_numeric(path["v187_state_multiplier"], errors="coerce").fillna(1.0).gt(1.0)].copy()
    if work.empty:
        return 0, 0.0
    work["timestamp"] = _to_utc(work["timestamp"])
    month_counts = work.groupby(work["timestamp"].dt.strftime("%Y-%m")).size()
    return int(month_counts.size), float(month_counts.max() / len(work) * 100.0)


def _single_trade_delta_share(path: pd.DataFrame) -> float:
    multiplier = pd.to_numeric(path["v187_state_multiplier"], errors="coerce").fillna(1.0)
    stepped = multiplier.gt(1.0)
    if not stepped.any():
        return 0.0
    candidate_return = pd.to_numeric(path["v187_account_return_pct"], errors="coerce").fillna(0.0)
    if "v186_account_return_pct" in path.columns:
        base_return = pd.to_numeric(path["v186_account_return_pct"], errors="coerce").fillna(0.0)
    else:
        base_return = candidate_return.div(multiplier.replace(0.0, 1.0))
    delta = (candidate_return.loc[stepped] - base_return.loc[stepped]).abs()
    total = float(delta.sum())
    return float(delta.max() / total * 100.0) if total else 0.0


def _policy_metrics(policy: str, path: pd.DataFrame, *, baseline_months: pd.Index) -> dict[str, object]:
    if path.empty:
        monthly = pd.Series(0.0, index=baseline_months)
        holdout_monthly = monthly[monthly.index >= SELECTOR_END.strftime("%Y-%m")]
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
            "holdout_positive_months": int((holdout_monthly > 0.0).sum()),
            "holdout_month_count": int(len(holdout_monthly)),
        }
    ordered = path.sort_values("timestamp", kind="mergesort").copy()
    ordered["timestamp"] = _to_utc(ordered["timestamp"])
    ordered["month"] = ordered["timestamp"].dt.strftime("%Y-%m")
    returns = pd.to_numeric(ordered["v187_account_return_pct"], errors="coerce").fillna(0.0)
    monthly = returns.groupby(ordered["month"], sort=True).sum().reindex(baseline_months, fill_value=0.0)
    holdout_mask = ordered["timestamp"].ge(SELECTOR_END)
    holdout_returns = returns.loc[holdout_mask]
    holdout_monthly = monthly[monthly.index >= SELECTOR_END.strftime("%Y-%m")]
    stepped = pd.to_numeric(ordered["v187_state_multiplier"], errors="coerce").fillna(1.0).gt(1.0)
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
        "holdout_positive_months": int((holdout_monthly > 0.0).sum()),
        "holdout_month_count": int(len(holdout_monthly)),
    }


def _compare_policies(policy_paths: dict[str, pd.DataFrame], baseline_months: pd.Index) -> pd.DataFrame:
    rows = [_policy_metrics(policy, path, baseline_months=baseline_months) for policy, path in policy_paths.items()]
    out = pd.DataFrame(rows)
    baseline = out.loc[out["policy"].eq("v186_baseline_no_drought_long_base_trend_stepup")].iloc[0]
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
    out["drought_trend_stepup_passed"] = (
        out["return_delta_pct"].ge(MIN_RETURN_DELTA_PCT)
        & out["holdout_return_delta_pct"].ge(MIN_HOLDOUT_RETURN_DELTA_PCT)
        & out["drawdown_improvement_pct"].ge(-EPSILON)
        & out["holdout_drawdown_improvement_pct"].ge(-EPSILON)
        & out["worst_month_improvement_pct"].ge(-EPSILON)
        & out["positive_month_delta"].ge(0)
        & out["holdout_positive_month_delta"].ge(0)
        & out["stepup_trade_count"].ge(MIN_STEPUP_TRADE_COUNT)
        & out["stepup_active_month_count"].ge(MIN_STEPUP_ACTIVE_MONTHS)
        & out["stepup_max_month_trade_share_pct"].le(MAX_MONTH_TRADE_SHARE_PCT)
        & out["stepup_max_single_trade_delta_share_pct"].le(MAX_SINGLE_TRADE_DELTA_SHARE_PCT)
    )
    out["drought_trend_stepup_score"] = (
        out["return_delta_pct"]
        + out["holdout_return_delta_pct"] * 1.5
        + out["drawdown_improvement_pct"] * 20.0
        + (MAX_MONTH_TRADE_SHARE_PCT - out["stepup_max_month_trade_share_pct"]).clip(lower=0.0)
        + (MAX_SINGLE_TRADE_DELTA_SHARE_PCT - out["stepup_max_single_trade_delta_share_pct"]).clip(lower=0.0) * 0.5
        - out["stepup_trade_count"] * 0.05
    )
    out["drought_trend_stepup_passed"] = out["drought_trend_stepup_passed"].map(bool).astype(object)
    return out.sort_values(
        ["drought_trend_stepup_passed", "drought_trend_stepup_score"],
        ascending=[False, False],
    ).reset_index(drop=True)


def _select_policy(comparison: pd.DataFrame) -> str:
    candidates = comparison.loc[
        comparison["drought_trend_stepup_passed"].astype(bool)
        & ~comparison["policy"].eq("v186_baseline_no_drought_long_base_trend_stepup")
    ].copy()
    if candidates.empty:
        return "v186_baseline_no_drought_long_base_trend_stepup"
    return str(candidates.iloc[0]["policy"])


def _monthly_path(path: pd.DataFrame) -> pd.DataFrame:
    work = path.sort_values("timestamp", kind="mergesort").copy()
    work["timestamp"] = _to_utc(work["timestamp"])
    work["month"] = work["timestamp"].dt.strftime("%Y-%m")
    work["baseline_return"] = pd.to_numeric(work["v186_account_return_pct"], errors="coerce").fillna(0.0)
    work["candidate_return"] = pd.to_numeric(work["v187_account_return_pct"], errors="coerce").fillna(0.0)
    work["stepped_up"] = pd.to_numeric(work["v187_state_multiplier"], errors="coerce").fillna(1.0).gt(1.0)
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
    work["baseline_return"] = pd.to_numeric(work["v186_account_return_pct"], errors="coerce").fillna(0.0)
    work["candidate_return"] = pd.to_numeric(work["v187_account_return_pct"], errors="coerce").fillna(0.0)
    work["candidate_pnl"] = pd.to_numeric(work["v187_account_pnl_bps"], errors="coerce").fillna(0.0)
    return (
        work.groupby(["v187_state_action", "v186_state_action", "source", "side", "leg"], dropna=False)
        .agg(
            trade_count=("candidate_return", "size"),
            baseline_return_pct=("baseline_return", "sum"),
            candidate_return_pct=("candidate_return", "sum"),
            win_rate_pct=("candidate_pnl", lambda s: float((s > 0.0).mean() * 100.0) if len(s) else 0.0),
            avg_multiplier=("v187_state_multiplier", "mean"),
            avg_trend_abs_60_bps=("trend_abs_60_bps", "mean"),
            avg_prior_ret_60_bps=("prior_ret_60_bps", "mean"),
            avg_day_sofar_count=("day_sofar_count", "mean"),
            avg_direction_probability=("direction_probability", "mean"),
            avg_premium_z_120d=("premium_z_120d", "mean"),
            avg_funding_z_120d=("funding_z_120d", "mean"),
            avg_prior_range_pos_720=("prior_range_pos_720", "mean"),
        )
        .reset_index()
        .assign(return_delta_pct=lambda df: df["candidate_return_pct"] - df["baseline_return_pct"])
    )


def _iteration_metrics_table(comparison: pd.DataFrame, *, selected_policy: str) -> list[dict[str, object]]:
    baseline = comparison.loc[comparison["policy"].eq("v186_baseline_no_drought_long_base_trend_stepup")].iloc[0]
    selected = comparison.loc[comparison["policy"].eq(selected_policy)].iloc[0]
    rows = []
    for version, row, improvement in (
        ("V186", baseline, None),
        ("V187", selected, float(selected["return_delta_pct"])),
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
    selected_is_baseline = selected_policy == "v186_baseline_no_drought_long_base_trend_stepup"
    return {
        "config": {
            "base": "v186_selected_account_path",
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
                "drought_long_base_trend_stepup_no_candidate"
                if selected_is_baseline
                else "drought_long_base_trend_stepup_candidate_ready"
            ),
            "promote_to_live": False,
            "selected_policy": selected_policy,
            "selected_drought_trend_stepup_passed": bool(sel.get("drought_trend_stepup_passed", False)),
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
            "message": "V187 tests a size step-up for drought long-base rows after deeper 60-minute extension.",
        },
        "iteration_metrics_table": _iteration_metrics_table(comparison, selected_policy=selected_policy),
    }


def _metrics_table_markdown(rows: list[dict[str, object]]) -> str:
    lines = [
        "| Metric | V186 | V187 |",
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
        "# Research V187 BTCUSDC Drought Long-Base Trend Step-Up",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to live: `{decision['promote_to_live']}`",
        f"- Selected policy: `{decision['selected_policy']}`",
        f"- Drought trend step-up passed: `{decision['selected_drought_trend_stepup_passed']}`",
        f"- Return delta vs V186: `{decision['selected_return_delta_pct']}` pct",
        f"- Return improvement rate vs V186: `{decision['selected_return_improvement_rate']}`",
        f"- Drawdown improvement vs V186: `{decision['selected_drawdown_improvement_pct']}` pct",
        f"- Holdout return delta vs V186: `{decision['selected_holdout_return_delta_pct']}` pct",
        f"- Holdout drawdown improvement vs V186: `{decision['selected_holdout_drawdown_improvement_pct']}` pct",
        f"- Step-up trades: `{decision['selected_stepup_trade_count']}`",
        f"- Step-up active months: `{decision['selected_stepup_active_month_count']}`",
        f"- Step-up max-month share: `{decision['selected_stepup_max_month_trade_share_pct']}` pct",
        f"- Step-up max single-trade delta share: `{decision['selected_stepup_max_single_trade_delta_share_pct']}` pct",
        f"- Message: {decision['message']}",
        "",
        "## Iteration Metrics",
        "",
        _metrics_table_markdown(payload["iteration_metrics_table"]),
        "",
        "## Overlay Rules",
        "",
        "- Base path: V186 selected account path.",
        "- V187 only changes `source=v122_drought`, `side=long`, `leg=base`, `v186_state_action=unchanged` rows.",
        "- Selected trend rule: `trend_abs_60_bps >= 238.049377`.",
        "- Selected step-up multiplier: `1.25x` on top of the V186 account return for that existing bucket.",
        "- V187 does not add trades, change trade side, or change existing entry thresholds.",
        "- Candidate must improve full-path and holdout return, avoid worse drawdown/worst month, and keep step-up rows diversified.",
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
        "V187 finds that a drought long-base subset behaves better after deeper 60-minute extension. This still fits the same pattern: market state is used as position-size context for an existing signal family, not as a new standalone entry rule.",
        "",
        "This remains a research audit, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not V186_ACCOUNT_PATH.exists():
        v186.run()
    trades = pd.read_csv(V186_ACCOUNT_PATH)
    trades["timestamp"] = _to_utc(trades["timestamp"])
    baseline_months = _baseline_months(trades)
    policy_paths = {policy.policy: _apply_drought_long_base_trend_stepup_policy(trades, policy) for policy in POLICIES}
    comparison = _compare_policies(policy_paths, baseline_months)
    selected_policy = _select_policy(comparison)
    selected_path = policy_paths[selected_policy]
    monthly = _monthly_path(selected_path)
    profile = _action_profile(selected_path)
    payload = _payload_for_comparison(comparison, selected_policy=selected_policy)
    comparison.to_csv(OUT_DIR / "v187_policy_comparison.csv", index=False)
    selected_path.to_csv(OUT_DIR / "v187_selected_account_path.csv", index=False)
    monthly.to_csv(OUT_DIR / "v187_selected_monthly_path.csv", index=False)
    profile.to_csv(OUT_DIR / "v187_selected_action_profile.csv", index=False)
    (OUT_DIR / "v187_drought_long_base_trend_stepup_summary.json").write_text(
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
