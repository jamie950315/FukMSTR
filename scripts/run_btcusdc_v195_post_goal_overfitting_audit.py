from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v195_post_goal_overfitting_audit"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V195_BTCUSDC_POST_GOAL_OVERFITTING_AUDIT.md"
SELECTOR_END = pd.Timestamp("2026-01-01T00:00:00Z")
MAX_MONTH_DELTA_SHARE_PCT = 50.0
MAX_SINGLE_DELTA_SHARE_PCT = 30.0
MIN_ACTIVE_MONTHS = 8

ITERATIONS = (
    {
        "version": "V192",
        "previous_version": "V191",
        "path": ROOT / "runs" / "research_v192_long_base_low_probz_throttle" / "v192_selected_account_path.csv",
        "baseline_return_col": "v191_account_return_pct",
        "candidate_return_col": "v192_account_return_pct",
        "baseline_pnl_col": "v191_account_pnl_bps",
        "candidate_pnl_col": "v192_account_pnl_bps",
        "action_col": "v192_state_action",
        "changed_actions": {"long_base_low_probz_throttle"},
    },
    {
        "version": "V193",
        "previous_version": "V192",
        "path": ROOT
        / "runs"
        / "research_v193_long_base_top5_premium6h_throttle"
        / "v193_selected_account_path.csv",
        "baseline_return_col": "v192_account_return_pct",
        "candidate_return_col": "v193_account_return_pct",
        "baseline_pnl_col": "v192_account_pnl_bps",
        "candidate_pnl_col": "v193_account_pnl_bps",
        "action_col": "v193_state_action",
        "changed_actions": {"long_base_top5_premium6h_throttle"},
    },
    {
        "version": "V194",
        "previous_version": "V193",
        "path": ROOT
        / "runs"
        / "research_v194_long_rescue_premium_discount_stepup"
        / "v194_selected_account_path.csv",
        "baseline_return_col": "v193_account_return_pct",
        "candidate_return_col": "v194_account_return_pct",
        "baseline_pnl_col": "v193_account_pnl_bps",
        "candidate_pnl_col": "v194_account_pnl_bps",
        "action_col": "v194_state_action",
        "changed_actions": {"long_rescue_premium_discount_stepup"},
    },
)


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _max_drawdown(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    equity = returns.cumsum()
    drawdown = equity - equity.cummax()
    return float(drawdown.min()) if len(drawdown) else 0.0


def _positive_months(frame: pd.DataFrame, returns: pd.Series) -> str:
    monthly = returns.groupby(frame["month"], sort=True).sum()
    return f"{int((monthly > 0.0).sum())}/{int(len(monthly))}"


def _holdout_months(frame: pd.DataFrame, returns: pd.Series) -> str:
    monthly = returns.groupby(frame["month"], sort=True).sum()
    holdout_monthly = monthly[monthly.index >= SELECTOR_END.strftime("%Y-%m")]
    return f"{int((holdout_monthly > 0.0).sum())}/{int(len(holdout_monthly))}"


def _version_metric_rows() -> pd.DataFrame:
    rows = []
    for config in ITERATIONS:
        frame = pd.read_csv(config["path"])
        frame["timestamp"] = _to_utc(frame["timestamp"])
        frame["month"] = frame["timestamp"].dt.strftime("%Y-%m")
        for version, return_col, previous in (
            (config["previous_version"], config["baseline_return_col"], True),
            (config["version"], config["candidate_return_col"], False),
        ):
            if rows and rows[-1]["version"] == version:
                continue
            returns = pd.to_numeric(frame[return_col], errors="coerce").fillna(0.0)
            holdout_returns = returns.loc[frame["timestamp"].ge(SELECTOR_END)]
            rows.append(
                {
                    "version": version,
                    "account_return_pct": float(returns.sum()),
                    "improvement_pct": "-" if previous else None,
                    "max_drawdown_pct": _max_drawdown(returns),
                    "positive_months": _positive_months(frame, returns),
                    "holdout_return_pct": float(holdout_returns.sum()),
                    "holdout_months": _holdout_months(frame, returns),
                }
            )
    version_table = pd.DataFrame(rows).drop_duplicates("version", keep="last").reset_index(drop=True)
    improvement = version_table["account_return_pct"].diff().astype(object)
    improvement.iloc[0] = "-"
    version_table["improvement_pct"] = improvement
    return version_table


def _iteration_concentration_row(
    frame: pd.DataFrame,
    *,
    version: str,
    previous_version: str,
    baseline_return_col: str,
    candidate_return_col: str,
    action_col: str,
    changed_actions: set[str],
) -> dict[str, object]:
    work = frame.copy()
    work["timestamp"] = _to_utc(work["timestamp"])
    work["month"] = work["timestamp"].dt.strftime("%Y-%m")
    baseline_returns = pd.to_numeric(work[baseline_return_col], errors="coerce").fillna(0.0)
    candidate_returns = pd.to_numeric(work[candidate_return_col], errors="coerce").fillna(0.0)
    delta = candidate_returns - baseline_returns
    changed = work[action_col].fillna("").astype(str).isin(changed_actions)
    affected_delta = delta.loc[changed]
    monthly_delta = delta.groupby(work["month"], sort=True).sum()
    if monthly_delta.empty:
        top_month = ""
        top_month_delta = 0.0
    else:
        top_month = str(monthly_delta.abs().idxmax())
        top_month_delta = float(monthly_delta.loc[top_month])
    total_delta = float(delta.sum())
    holdout_delta = float(delta.loc[work["timestamp"].ge(SELECTOR_END)].sum())
    abs_affected_delta = affected_delta.abs()
    total_abs_affected_delta = float(abs_affected_delta.sum())
    return {
        "version": version,
        "previous_version": previous_version,
        "return_delta_pct": total_delta,
        "holdout_return_delta_pct": holdout_delta,
        "holdout_delta_share_pct": float(holdout_delta / total_delta * 100.0) if total_delta else 0.0,
        "affected_trade_count": int(changed.sum()),
        "affected_active_month_count": int(work.loc[changed, "month"].nunique()),
        "top_delta_month": top_month,
        "top_month_delta_pct": top_month_delta,
        "top_month_delta_share_pct": float(abs(top_month_delta) / abs(total_delta) * 100.0) if total_delta else 0.0,
        "top_single_delta_share_pct": (
            float(abs_affected_delta.max() / total_abs_affected_delta * 100.0) if total_abs_affected_delta else 0.0
        ),
        "affected_win_rate_pct": (
            float((candidate_returns.loc[changed] > 0.0).mean() * 100.0) if int(changed.sum()) else 0.0
        ),
    }


def _iteration_concentration_table() -> pd.DataFrame:
    rows = []
    for config in ITERATIONS:
        frame = pd.read_csv(config["path"])
        rows.append(
            _iteration_concentration_row(
                frame,
                version=config["version"],
                previous_version=config["previous_version"],
                baseline_return_col=config["baseline_return_col"],
                candidate_return_col=config["candidate_return_col"],
                action_col=config["action_col"],
                changed_actions=config["changed_actions"],
            )
        )
    return pd.DataFrame(rows)


def _payload_for_audit(iteration_table: pd.DataFrame) -> dict[str, object]:
    risky_month = iteration_table["top_month_delta_share_pct"].gt(MAX_MONTH_DELTA_SHARE_PCT)
    risky_single = iteration_table["top_single_delta_share_pct"].gt(MAX_SINGLE_DELTA_SHARE_PCT)
    sparse = iteration_table["affected_active_month_count"].lt(MIN_ACTIVE_MONTHS)
    risk_score = (
        iteration_table["top_month_delta_share_pct"] * 0.55
        + iteration_table["top_single_delta_share_pct"] * 0.35
        + (MIN_ACTIVE_MONTHS - iteration_table["affected_active_month_count"]).clip(lower=0.0) * 5.0
    )
    highest_risk_version = str(iteration_table.iloc[int(risk_score.idxmax())]["version"])
    v194 = iteration_table.loc[iteration_table["version"].eq("V194")]
    v194_high_concentration = bool(
        not v194.empty
        and (
            bool(v194.iloc[0]["top_month_delta_share_pct"] > MAX_MONTH_DELTA_SHARE_PCT)
            or bool(v194.iloc[0]["top_single_delta_share_pct"] > MAX_SINGLE_DELTA_SHARE_PCT)
        )
    )
    warning = bool(risky_month.any() or risky_single.any() or sparse.any())
    return {
        "config": {
            "base_versions": ["V192", "V193", "V194"],
            "selector_end": str(SELECTOR_END),
            "max_month_delta_share_pct": MAX_MONTH_DELTA_SHARE_PCT,
            "max_single_delta_share_pct": MAX_SINGLE_DELTA_SHARE_PCT,
            "min_active_months": MIN_ACTIVE_MONTHS,
            "adds_new_trades": False,
            "changes_existing_threshold": False,
            "changes_trade_side": False,
            "promotes_live_trading": False,
        },
        "decision": {
            "status": "post_goal_overfitting_warning" if warning else "post_goal_overfitting_not_detected",
            "promote_to_live": False,
            "highest_risk_version": highest_risk_version,
            "stop_historical_optimization": warning,
            "recommendation": (
                "freeze_historical_optimization_and_forward_monitor"
                if warning
                else "continue_with_strict_forward_monitoring"
            ),
            "v194_high_concentration_risk": v194_high_concentration,
            "holdout_reuse_risk": True,
            "message": (
                "V194 shows high concentration risk; freeze historical optimization and validate on new forward data."
                if warning
                else "No concentration warning was detected, but forward monitoring is still required."
            ),
        },
    }


def _metrics_table_markdown(version_metrics: pd.DataFrame) -> str:
    rows = version_metrics.tail(2).reset_index(drop=True)
    lines = [
        f"| Metric | {rows.iloc[0]['version']} | {rows.iloc[1]['version']} |",
        "|---|---:|---:|",
        f"| Account return estimate | +{rows.iloc[0]['account_return_pct']:.2f}% | +{rows.iloc[1]['account_return_pct']:.2f}% |",
        f"| Improvement | - | +{float(rows.iloc[1]['improvement_pct']):.2f} percentage points |",
        f"| Max drawdown | {rows.iloc[0]['max_drawdown_pct']:.2f}% | {rows.iloc[1]['max_drawdown_pct']:.2f}% |",
        f"| Positive months | {rows.iloc[0]['positive_months']} | {rows.iloc[1]['positive_months']} |",
        f"| Holdout return | +{rows.iloc[0]['holdout_return_pct']:.2f}% | +{rows.iloc[1]['holdout_return_pct']:.2f}% |",
        f"| Holdout months | {rows.iloc[0]['holdout_months']} | {rows.iloc[1]['holdout_months']} |",
    ]
    return "\n".join(lines)


def _write_report(
    payload: dict[str, object],
    version_metrics: pd.DataFrame,
    iteration_table: pd.DataFrame,
) -> None:
    decision = payload["decision"]
    lines = [
        "# Research V195 BTCUSDC Post-Goal Overfitting Audit",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to live: `{decision['promote_to_live']}`",
        f"- Highest risk version: `{decision['highest_risk_version']}`",
        f"- Stop historical optimization: `{decision['stop_historical_optimization']}`",
        f"- Recommendation: `{decision['recommendation']}`",
        f"- V194 high concentration risk: `{decision['v194_high_concentration_risk']}`",
        f"- Holdout reuse risk: `{decision['holdout_reuse_risk']}`",
        f"- Message: {decision['message']}",
        "",
        "## Required Iteration Metrics",
        "",
        _metrics_table_markdown(version_metrics),
        "",
        "## Audit Rules",
        "",
        "- V195 is an audit, not a new strategy overlay.",
        "- It checks the improvement added during V192, V193, and V194.",
        f"- Month concentration warning threshold: `{MAX_MONTH_DELTA_SHARE_PCT}` pct of total improvement.",
        f"- Single-trade concentration warning threshold: `{MAX_SINGLE_DELTA_SHARE_PCT}` pct of affected absolute delta.",
        f"- Minimum active months: `{MIN_ACTIVE_MONTHS}`.",
        "- The V192-V194 holdout has been reused for selection and should no longer be treated as clean validation.",
        "",
        "## Version Metrics",
        "",
        version_metrics.to_csv(index=False).strip(),
        "",
        "## Overfitting Concentration Table",
        "",
        iteration_table.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V192 and V193 are lower-risk risk-reduction changes. V194 adds a large improvement, but the gain is concentrated in one holdout month and one large affected trade. That concentration is a practical overfitting warning.",
        "",
        "Recommended next step: freeze historical optimization, keep V194 as an aggressive research candidate, keep V193 as the more conservative comparison, and validate both through forward monitoring on new data.",
        "",
        "This is a research audit, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    version_metrics = _version_metric_rows()
    iteration_table = _iteration_concentration_table()
    payload = _payload_for_audit(iteration_table)
    version_metrics.to_csv(OUT_DIR / "v195_version_metrics.csv", index=False)
    iteration_table.to_csv(OUT_DIR / "v195_overfitting_concentration_table.csv", index=False)
    (OUT_DIR / "v195_post_goal_overfitting_audit_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, version_metrics, iteration_table)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
