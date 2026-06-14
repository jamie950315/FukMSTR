from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v162_long_trend_follow_boost as v162


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v173_timestamp_side_exposure_cap"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V173_BTCUSDC_TIMESTAMP_SIDE_EXPOSURE_CAP.md"
V162_ACCOUNT_PATH = ROOT / "runs" / "research_v162_long_trend_follow_boost" / "v162_selected_account_path.csv"
MIN_RETURN_RETENTION_RATE = 0.99
MIN_DRAWDOWN_IMPROVEMENT_PCT = 5.0


@dataclass(frozen=True)
class TimestampSideExposurePolicy:
    policy: str
    max_timestamp_side_weight: float


POLICIES = (
    TimestampSideExposurePolicy("v162_baseline_no_timestamp_side_cap", 999.0),
    TimestampSideExposurePolicy("v173_cap_weight_8p0", 8.0),
    TimestampSideExposurePolicy("v173_cap_weight_6p0", 6.0),
    TimestampSideExposurePolicy("v173_cap_weight_5p0", 5.0),
    TimestampSideExposurePolicy("v173_cap_weight_4p0", 4.0),
    TimestampSideExposurePolicy("v173_cap_weight_3p5", 3.5),
    TimestampSideExposurePolicy("v173_cap_weight_3p0", 3.0),
    TimestampSideExposurePolicy("v173_cap_weight_2p5", 2.5),
)


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _annotate_timestamp_side_exposure(trades: pd.DataFrame) -> pd.DataFrame:
    out = trades.sort_values("timestamp", kind="mergesort").reset_index(drop=True).copy()
    out["timestamp"] = _to_utc(out["timestamp"])
    out["position_weight"] = pd.to_numeric(out.get("position_weight", 1.0), errors="coerce").fillna(1.0)
    grouped = out.groupby(["timestamp", "side"], dropna=False)["position_weight"]
    out["v173_timestamp_side_position_weight"] = grouped.transform("sum")
    out["v173_timestamp_side_trade_count"] = grouped.transform("size")
    return out


def _apply_timestamp_side_cap(
    trades: pd.DataFrame,
    policy: TimestampSideExposurePolicy,
) -> pd.DataFrame:
    out = trades.copy()
    if "v173_timestamp_side_position_weight" not in out.columns:
        out = _annotate_timestamp_side_exposure(out)
    group_weight = pd.to_numeric(out["v173_timestamp_side_position_weight"], errors="coerce").fillna(0.0)
    cap = float(policy.max_timestamp_side_weight)
    multiplier = (cap / group_weight).clip(upper=1.0)
    multiplier = multiplier.where(group_weight > 0.0, 1.0)
    base_return = pd.to_numeric(out["v162_account_return_pct"], errors="coerce").fillna(0.0)
    base_pnl = pd.to_numeric(out["v162_account_pnl_bps"], errors="coerce").fillna(0.0)
    out["v173_policy"] = policy.policy
    out["v173_cap_weight"] = cap
    out["v173_cap_applied"] = multiplier < 1.0
    out["v173_exposure_multiplier"] = multiplier
    out["v173_account_return_pct"] = base_return * multiplier
    out["v173_account_pnl_bps"] = base_pnl * multiplier
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
            "capped_trade_count": 0,
            "capped_group_count": 0,
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
    returns = pd.to_numeric(ordered["v173_account_return_pct"], errors="coerce").fillna(0.0)
    pnl = pd.to_numeric(ordered["v173_account_pnl_bps"], errors="coerce").fillna(0.0)
    equity = returns.cumsum()
    drawdown = equity - equity.cummax()
    monthly = returns.groupby(ordered["month"], sort=True).sum().reindex(baseline_months, fill_value=0.0)
    capped = ordered["v173_cap_applied"].fillna(False).astype(bool)
    capped_groups = ordered.loc[capped, ["timestamp", "side"]].drop_duplicates()
    return {
        "policy": policy,
        "trade_count": int(len(ordered)),
        "capped_trade_count": int(capped.sum()),
        "capped_group_count": int(len(capped_groups)),
        "total_account_return_pct": float(returns.sum()),
        "max_drawdown_pct": float(drawdown.min()) if len(drawdown) else 0.0,
        "positive_months": int((monthly > 0.0).sum()),
        "month_count": int(len(monthly)),
        "worst_month_pct": float(monthly.min()) if len(monthly) else 0.0,
        "win_rate_pct": float((pnl > 0.0).mean() * 100.0) if len(pnl) else 0.0,
    }


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


def _compare_policies(policy_paths: dict[str, pd.DataFrame], baseline_months: pd.Index) -> pd.DataFrame:
    rows = [_policy_metrics(policy, path, baseline_months=baseline_months) for policy, path in policy_paths.items()]
    out = pd.DataFrame(rows)
    baseline = out.loc[out["policy"].eq("v162_baseline_no_timestamp_side_cap")].iloc[0]
    out["return_delta_pct"] = out["total_account_return_pct"] - float(baseline["total_account_return_pct"])
    out["return_retention_rate"] = out["total_account_return_pct"] / float(baseline["total_account_return_pct"])
    out["drawdown_improvement_pct"] = out["max_drawdown_pct"] - float(baseline["max_drawdown_pct"])
    out["worst_month_improvement_pct"] = out["worst_month_pct"] - float(baseline["worst_month_pct"])
    out["positive_month_delta"] = out["positive_months"] - int(baseline["positive_months"])
    out["cap_passed"] = (
        out["return_retention_rate"].ge(MIN_RETURN_RETENTION_RATE)
        & out["drawdown_improvement_pct"].ge(MIN_DRAWDOWN_IMPROVEMENT_PCT)
        & out["worst_month_improvement_pct"].ge(0.0)
        & out["positive_month_delta"].ge(0)
    )
    out["cap_score"] = (
        out["drawdown_improvement_pct"] * 10.0
        + out["worst_month_improvement_pct"] * 5.0
        + out["return_delta_pct"] / 50.0
        - out["capped_group_count"] * 0.1
    )
    return out.sort_values(["cap_passed", "cap_score"], ascending=[False, False]).reset_index(drop=True)


def _select_policy(comparison: pd.DataFrame) -> str:
    candidates = comparison.loc[
        comparison["cap_passed"].astype(bool)
        & ~comparison["policy"].eq("v162_baseline_no_timestamp_side_cap")
    ].copy()
    if candidates.empty:
        return "v162_baseline_no_timestamp_side_cap"
    return str(candidates.iloc[0]["policy"])


def _capped_profile(path: pd.DataFrame) -> pd.DataFrame:
    work = path.copy()
    work["win"] = pd.to_numeric(work["v173_account_return_pct"], errors="coerce").fillna(0.0) > 0.0
    return (
        work.groupby(["v173_policy", "v173_cap_applied", "side", "leg"], dropna=False)
        .agg(
            trade_count=("v173_account_return_pct", "size"),
            account_return_pct=("v173_account_return_pct", "sum"),
            original_account_return_pct=("v162_account_return_pct", "sum"),
            win_rate_pct=("win", "mean"),
            avg_timestamp_side_weight=("v173_timestamp_side_position_weight", "mean"),
            avg_multiplier=("v173_exposure_multiplier", "mean"),
        )
        .reset_index()
        .assign(win_rate_pct=lambda df: df["win_rate_pct"] * 100.0)
    )


def _payload_for_comparison(comparison: pd.DataFrame, *, selected_policy: str) -> dict[str, object]:
    baseline = comparison.loc[comparison["policy"].eq("v162_baseline_no_timestamp_side_cap")]
    selected = comparison.loc[comparison["policy"].eq(selected_policy)]
    base = baseline.iloc[0] if not baseline.empty else pd.Series(dtype=object)
    sel = selected.iloc[0] if not selected.empty else pd.Series(dtype=object)
    selected_is_baseline = selected_policy == "v162_baseline_no_timestamp_side_cap"
    return {
        "config": {
            "base": "v162_selected_account_path",
            "min_return_retention_rate": MIN_RETURN_RETENTION_RATE,
            "min_drawdown_improvement_pct": MIN_DRAWDOWN_IMPROVEMENT_PCT,
            "adds_new_trades": False,
            "changes_existing_threshold": False,
            "changes_trade_side": False,
            "promotes_live_trading": False,
        },
        "decision": {
            "status": (
                "timestamp_side_exposure_cap_no_candidate"
                if selected_is_baseline
                else "timestamp_side_exposure_cap_candidate_ready"
            ),
            "promote_to_live": False,
            "selected_policy": selected_policy,
            "selected_return_delta_pct": float(sel.get("total_account_return_pct", 0.0))
            - float(base.get("total_account_return_pct", 0.0)),
            "selected_drawdown_improvement_pct": float(sel.get("max_drawdown_pct", 0.0))
            - float(base.get("max_drawdown_pct", 0.0)),
            "selected_worst_month_improvement_pct": float(sel.get("worst_month_pct", 0.0))
            - float(base.get("worst_month_pct", 0.0)),
            "selected_capped_trade_count": int(sel.get("capped_trade_count", 0)),
            "selected_capped_group_count": int(sel.get("capped_group_count", 0)),
            "message": "Timestamp-side exposure caps are evaluated as causal sizing guards only, not as new entry signals.",
        },
    }


def _write_report(
    payload: dict[str, object],
    comparison: pd.DataFrame,
    selected_profile: pd.DataFrame,
    selected_drawdown: dict[str, object],
    baseline_drawdown: dict[str, object],
) -> None:
    decision = payload["decision"]
    lines = [
        "# Research V173 BTCUSDC Timestamp Side Exposure Cap",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to live: `{decision['promote_to_live']}`",
        f"- Selected policy: `{decision['selected_policy']}`",
        f"- Return delta: `{decision['selected_return_delta_pct']}` pct",
        f"- Drawdown improvement: `{decision['selected_drawdown_improvement_pct']}` pct",
        f"- Worst-month improvement: `{decision['selected_worst_month_improvement_pct']}` pct",
        f"- Capped trades: `{decision['selected_capped_trade_count']}`",
        f"- Capped timestamp-side groups: `{decision['selected_capped_group_count']}`",
        f"- Message: {decision['message']}",
        "",
        "## Cap Rules",
        "",
        "- Base path: V162 selected account path.",
        "- Cap unit: same timestamp and same side.",
        "- Cap action: scale all trades in the timestamp-side group by `cap / group_position_weight` when the group exceeds the cap.",
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
        "## Selected Capped Profile",
        "",
        selected_profile.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V173 tests whether simultaneous same-side source stacking explains the V171 max-drawdown cluster better than prior rescue-count guards. Use the result as risk-research evidence only. It does not prove future live performance.",
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
    baseline_months = _baseline_months(trades)
    annotated = _annotate_timestamp_side_exposure(trades)
    policy_paths = {policy.policy: _apply_timestamp_side_cap(annotated, policy) for policy in POLICIES}
    comparison = _compare_policies(policy_paths, baseline_months)
    selected_policy = _select_policy(comparison)
    payload = _payload_for_comparison(comparison, selected_policy=selected_policy)
    selected_path = policy_paths[selected_policy]
    baseline_path = policy_paths["v162_baseline_no_timestamp_side_cap"]
    selected_profile = _capped_profile(selected_path)
    selected_drawdown = _max_drawdown_summary(selected_path, return_col="v173_account_return_pct")
    baseline_drawdown = _max_drawdown_summary(baseline_path, return_col="v173_account_return_pct")
    for policy_name, path in policy_paths.items():
        path.to_csv(OUT_DIR / f"{policy_name}_path.csv", index=False)
    comparison.to_csv(OUT_DIR / "v173_policy_comparison.csv", index=False)
    selected_profile.to_csv(OUT_DIR / "v173_selected_capped_profile.csv", index=False)
    pd.DataFrame([baseline_drawdown]).to_csv(OUT_DIR / "v173_baseline_max_drawdown.csv", index=False)
    pd.DataFrame([selected_drawdown]).to_csv(OUT_DIR / "v173_selected_max_drawdown.csv", index=False)
    (OUT_DIR / "v173_timestamp_side_exposure_cap_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, comparison, selected_profile, selected_drawdown, baseline_drawdown)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
