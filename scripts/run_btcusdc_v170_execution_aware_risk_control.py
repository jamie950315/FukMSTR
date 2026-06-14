from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v162_long_trend_follow_boost as v162
import run_btcusdc_v168_execution_readiness_gate as v168


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v170_execution_aware_risk_control"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V170_BTCUSDC_EXECUTION_AWARE_RISK_CONTROL.md"
V162_ACCOUNT_PATH = ROOT / "runs" / "research_v162_long_trend_follow_boost" / "v162_selected_account_path.csv"
V168_GATE_PATH = ROOT / "runs" / "research_v168_execution_readiness_gate" / "v168_execution_readiness_gate.csv"
MIN_RETURN_RETENTION_RATE = 0.995


@dataclass(frozen=True)
class ExecutionRiskPolicy:
    policy: str
    maker_only_multiplier: float
    maker_priority_multiplier: float
    no_trade_multiplier: float


POLICIES = (
    ExecutionRiskPolicy(
        policy="v162_baseline_no_execution_filter",
        maker_only_multiplier=1.0,
        maker_priority_multiplier=1.0,
        no_trade_multiplier=1.0,
    ),
    ExecutionRiskPolicy(
        policy="v170_maker_only_skip",
        maker_only_multiplier=0.0,
        maker_priority_multiplier=1.0,
        no_trade_multiplier=0.0,
    ),
    ExecutionRiskPolicy(
        policy="v170_maker_only_skip_priority_half",
        maker_only_multiplier=0.0,
        maker_priority_multiplier=0.5,
        no_trade_multiplier=0.0,
    ),
    ExecutionRiskPolicy(
        policy="v170_fragile_half",
        maker_only_multiplier=0.5,
        maker_priority_multiplier=0.5,
        no_trade_multiplier=0.0,
    ),
    ExecutionRiskPolicy(
        policy="v170_fragile_skip",
        maker_only_multiplier=0.0,
        maker_priority_multiplier=0.0,
        no_trade_multiplier=0.0,
    ),
)


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _attach_execution_mode(trades: pd.DataFrame, gate: pd.DataFrame) -> pd.DataFrame:
    gate_cols = ["month", "execution_readiness_mode", "live_gate_action"]
    available_cols = [col for col in gate_cols if col in gate.columns]
    out = trades.merge(gate[available_cols], on="month", how="left", validate="many_to_one").copy()
    out["execution_readiness_mode"] = out["execution_readiness_mode"].fillna("unknown_execution_mode")
    out["live_gate_action"] = out["live_gate_action"].fillna("investigate_missing_gate")
    return out


def _execution_multiplier(mode: pd.Series, policy: ExecutionRiskPolicy) -> pd.Series:
    out = pd.Series(1.0, index=mode.index)
    out.loc[mode.eq("maker_only_required")] = float(policy.maker_only_multiplier)
    out.loc[mode.eq("maker_priority_required")] = float(policy.maker_priority_multiplier)
    out.loc[mode.eq("no_trade_unless_cost_improves")] = float(policy.no_trade_multiplier)
    return out


def _apply_execution_risk_policy(
    trades: pd.DataFrame,
    gate: pd.DataFrame,
    policy: ExecutionRiskPolicy,
) -> pd.DataFrame:
    out = _attach_execution_mode(trades, gate)
    multiplier = _execution_multiplier(out["execution_readiness_mode"], policy)
    base_return = pd.to_numeric(out["v162_account_return_pct"], errors="coerce").fillna(0.0)
    base_pnl = pd.to_numeric(out["v162_account_pnl_bps"], errors="coerce").fillna(0.0)
    out["v170_policy"] = policy.policy
    out["v170_execution_multiplier"] = multiplier
    out["v170_executed_trade"] = multiplier > 0.0
    out["v170_account_return_pct"] = base_return * multiplier
    out["v170_account_pnl_bps"] = base_pnl * multiplier
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
            "executed_trade_count": 0,
            "skipped_trade_count": 0,
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
    returns = pd.to_numeric(ordered["v170_account_return_pct"], errors="coerce").fillna(0.0)
    pnl = pd.to_numeric(ordered["v170_account_pnl_bps"], errors="coerce").fillna(0.0)
    executed = ordered["v170_executed_trade"].fillna(False).astype(bool)
    equity = returns.cumsum()
    drawdown = equity - equity.cummax()
    monthly = returns.groupby(ordered["month"], sort=True).sum().reindex(baseline_months, fill_value=0.0)
    executed_pnl = pnl.loc[executed]
    return {
        "policy": policy,
        "trade_count": int(len(ordered)),
        "executed_trade_count": int(executed.sum()),
        "skipped_trade_count": int((~executed).sum()),
        "total_account_return_pct": float(returns.sum()),
        "max_drawdown_pct": float(drawdown.min()) if len(drawdown) else 0.0,
        "positive_months": int((monthly > 0.0).sum()),
        "month_count": int(len(monthly)),
        "worst_month_pct": float(monthly.min()) if len(monthly) else 0.0,
        "win_rate_pct": float((executed_pnl > 0.0).mean() * 100.0) if len(executed_pnl) else 0.0,
    }


def _compare_policies(policy_paths: dict[str, pd.DataFrame], baseline_months: pd.Index) -> pd.DataFrame:
    rows = [_policy_metrics(policy, path, baseline_months=baseline_months) for policy, path in policy_paths.items()]
    out = pd.DataFrame(rows)
    baseline = out.loc[out["policy"].eq("v162_baseline_no_execution_filter")].iloc[0]
    out["return_delta_pct"] = out["total_account_return_pct"] - float(baseline["total_account_return_pct"])
    out["return_retention_rate"] = out["total_account_return_pct"] / float(baseline["total_account_return_pct"])
    out["drawdown_improvement_pct"] = out["max_drawdown_pct"] - float(baseline["max_drawdown_pct"])
    out["worst_month_improvement_pct"] = out["worst_month_pct"] - float(baseline["worst_month_pct"])
    out["positive_month_delta"] = out["positive_months"] - int(baseline["positive_months"])
    out["executed_trade_delta"] = out["executed_trade_count"] - int(baseline["executed_trade_count"])
    out["risk_control_passed"] = (
        out["return_retention_rate"].ge(MIN_RETURN_RETENTION_RATE)
        & out["drawdown_improvement_pct"].ge(0.0)
        & out["worst_month_improvement_pct"].ge(0.0)
    )
    out["risk_control_score"] = (
        out["drawdown_improvement_pct"] * 10.0
        + out["worst_month_improvement_pct"] * 5.0
        + out["positive_month_delta"] * 2.0
        + out["return_delta_pct"] / 100.0
    )
    return out.sort_values(["risk_control_passed", "risk_control_score"], ascending=[False, False]).reset_index(drop=True)


def _select_policy(comparison: pd.DataFrame) -> str:
    candidates = comparison.loc[
        comparison["risk_control_passed"].astype(bool)
        & ~comparison["policy"].eq("v162_baseline_no_execution_filter")
    ].copy()
    if candidates.empty:
        return "v162_baseline_no_execution_filter"
    return str(candidates.iloc[0]["policy"])


def _mode_profile(path: pd.DataFrame) -> pd.DataFrame:
    work = path.copy()
    work["win"] = pd.to_numeric(work["v170_account_return_pct"], errors="coerce").fillna(0.0) > 0.0
    return (
        work.groupby(["v170_policy", "execution_readiness_mode", "live_gate_action"], dropna=False)
        .agg(
            trade_count=("v170_account_return_pct", "size"),
            executed_trade_count=("v170_executed_trade", "sum"),
            account_return_pct=("v170_account_return_pct", "sum"),
            account_pnl_bps=("v170_account_pnl_bps", "sum"),
            win_rate_pct=("win", "mean"),
            avg_execution_multiplier=("v170_execution_multiplier", "mean"),
        )
        .reset_index()
        .assign(win_rate_pct=lambda df: df["win_rate_pct"] * 100.0)
    )


def _payload_for_comparison(comparison: pd.DataFrame, *, selected_policy: str) -> dict[str, object]:
    baseline = comparison.loc[comparison["policy"].eq("baseline")]
    if baseline.empty:
        baseline = comparison.loc[comparison["policy"].eq("v162_baseline_no_execution_filter")]
    selected = comparison.loc[comparison["policy"].eq(selected_policy)]
    base = baseline.iloc[0] if not baseline.empty else pd.Series(dtype=object)
    sel = selected.iloc[0] if not selected.empty else pd.Series(dtype=object)
    selected_is_baseline = selected_policy in {"baseline", "v162_baseline_no_execution_filter"}
    return {
        "config": {
            "base": "v162_trades_joined_to_v168_execution_gate",
            "min_return_retention_rate": MIN_RETURN_RETENTION_RATE,
            "adds_new_trades": False,
            "changes_existing_threshold": False,
            "changes_trade_side": False,
            "promotes_live_trading": False,
        },
        "decision": {
            "status": (
                "execution_aware_risk_control_no_candidate"
                if selected_is_baseline
                else "execution_aware_risk_control_candidate_ready"
            ),
            "promote_to_live": False,
            "selected_policy": selected_policy,
            "selected_return_delta_pct": float(sel.get("total_account_return_pct", 0.0))
            - float(base.get("total_account_return_pct", 0.0)),
            "selected_drawdown_improvement_pct": float(sel.get("max_drawdown_pct", 0.0))
            - float(base.get("max_drawdown_pct", 0.0)),
            "selected_worst_month_improvement_pct": float(sel.get("worst_month_pct", 0.0))
            - float(base.get("worst_month_pct", 0.0)),
            "selected_executed_trade_count": int(sel.get("executed_trade_count", 0)),
            "baseline_executed_trade_count": int(base.get("executed_trade_count", 0)),
            "message": "Execution-aware controls are evaluated as risk controls only, not as new entry signals.",
        },
    }


def _write_report(
    payload: dict[str, object],
    comparison: pd.DataFrame,
    selected_monthly: pd.DataFrame,
    mode_profile: pd.DataFrame,
) -> None:
    decision = payload["decision"]
    lines = [
        "# Research V170 BTCUSDC Execution-Aware Risk Control",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to live: `{decision['promote_to_live']}`",
        f"- Selected policy: `{decision['selected_policy']}`",
        f"- Return delta: `{decision['selected_return_delta_pct']}` pct",
        f"- Drawdown improvement: `{decision['selected_drawdown_improvement_pct']}` pct",
        f"- Worst-month improvement: `{decision['selected_worst_month_improvement_pct']}` pct",
        f"- Executed trades: `{decision['selected_executed_trade_count']}` / `{decision['baseline_executed_trade_count']}` baseline",
        f"- Message: {decision['message']}",
        "",
        "## Policy Rules",
        "",
        "- Base trades: V162 selected account path.",
        "- Execution mode: V168 monthly execution readiness gate.",
        "- V170 does not add trades, change side, change threshold, or promote live trading.",
        "- Policies only scale or skip existing trades in maker-only, maker-priority, or no-trade-unless-cost-improves months.",
        "",
        "## Policy Comparison",
        "",
        comparison.to_csv(index=False).strip(),
        "",
        "## Selected Monthly Path",
        "",
        selected_monthly.to_csv(index=False).strip(),
        "",
        "## Selected Mode Profile",
        "",
        mode_profile.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V170 checks whether V169 fragile execution months should be treated as a risk-control layer. The result should be used as execution context only. It is not evidence that market emotion or trend should become a standalone entry signal.",
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
    if not V168_GATE_PATH.exists():
        v168.run()
    trades = pd.read_csv(V162_ACCOUNT_PATH)
    gate = pd.read_csv(V168_GATE_PATH)
    baseline_months = _baseline_months(trades)
    policy_paths = {policy.policy: _apply_execution_risk_policy(trades, gate, policy) for policy in POLICIES}
    comparison = _compare_policies(policy_paths, baseline_months)
    selected_policy = _select_policy(comparison)
    payload = _payload_for_comparison(comparison, selected_policy=selected_policy)
    selected_path = policy_paths[selected_policy]
    selected_monthly = (
        selected_path.assign(timestamp=_to_utc(selected_path["timestamp"]))
        .assign(month=lambda df: df["timestamp"].dt.strftime("%Y-%m"))
        .groupby(["month", "execution_readiness_mode", "live_gate_action"], sort=True, dropna=False)
        .agg(
            trade_count=("v170_account_return_pct", "size"),
            executed_trade_count=("v170_executed_trade", "sum"),
            account_return_pct=("v170_account_return_pct", "sum"),
            account_pnl_bps=("v170_account_pnl_bps", "sum"),
            avg_execution_multiplier=("v170_execution_multiplier", "mean"),
        )
        .reset_index()
    )
    selected_mode_profile = _mode_profile(selected_path)
    for policy_name, path in policy_paths.items():
        path.to_csv(OUT_DIR / f"{policy_name}_path.csv", index=False)
    comparison.to_csv(OUT_DIR / "v170_policy_comparison.csv", index=False)
    selected_monthly.to_csv(OUT_DIR / "v170_selected_monthly_path.csv", index=False)
    selected_mode_profile.to_csv(OUT_DIR / "v170_selected_mode_profile.csv", index=False)
    (OUT_DIR / "v170_execution_aware_risk_control_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, comparison, selected_monthly, selected_mode_profile)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
