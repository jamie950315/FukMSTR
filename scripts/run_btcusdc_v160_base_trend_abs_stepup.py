from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v144_funding_sentiment_governor as v144
import run_btcusdc_v159_base_trend_abs_boost as v159


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v160_base_trend_abs_stepup"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V160_BTCUSDC_BASE_TREND_ABS_STEPUP.md"
V159_ACCOUNT_PATH = ROOT / "runs" / "research_v159_base_trend_abs_boost" / "v159_selected_account_path.csv"
SELECTOR_END = pd.Timestamp("2026-01-01T00:00:00Z")
MIN_CHANGED_SELECTOR_TRADES = 60
MIN_CHANGED_HOLDOUT_TRADES = 20
MIN_INCREMENTAL_IMPROVEMENT_RATE = 1.01
STEPUP_MODIFIER = 1.05


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _apply_stepup(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    flag = out["v159_base_trend_abs_boost_flag"].fillna(False).astype(bool)
    modifier = pd.Series(1.0, index=out.index)
    modifier.loc[flag] = STEPUP_MODIFIER
    out["v160_base_trend_abs_stepup_flag"] = flag
    out["v160_modifier"] = modifier
    out["v160_account_return_pct"] = out["v159_account_return_pct"] * modifier
    out["v160_account_pnl_bps"] = out["v159_account_pnl_bps"] * modifier
    return out


def _period_masks(frame: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "full": pd.Series(True, index=frame.index),
        "selector": frame["timestamp"] < SELECTOR_END,
        "holdout": frame["timestamp"] >= SELECTOR_END,
    }


def _baseline_metrics(frame: pd.DataFrame, masks: dict[str, pd.Series]) -> tuple[dict[str, dict[str, object]], dict[str, pd.Index]]:
    metrics: dict[str, dict[str, object]] = {}
    months: dict[str, pd.Index] = {}
    for period, mask in masks.items():
        period_path = frame.loc[mask].copy()
        months[period] = v144.v143._month_index(period_path)
        metrics[period] = v144.v143._account_metrics(
            f"v159_{period}",
            period_path,
            return_col="v159_account_return_pct",
            pnl_col="v159_account_pnl_bps",
            baseline_months=months[period],
        )
    return metrics, months


def _candidate_metrics(
    baseline_path: pd.DataFrame,
    candidate_path: pd.DataFrame,
    *,
    masks: dict[str, pd.Series],
    baseline_metrics: dict[str, dict[str, object]],
    baseline_months: dict[str, pd.Index],
) -> dict[str, object]:
    changed = candidate_path["v160_modifier"] != 1.0
    flag = candidate_path["v160_base_trend_abs_stepup_flag"]
    row: dict[str, object] = {
        "candidate": "v160_base_trend_abs_stepup",
        "source_flag": "v159_base_trend_abs_boost_flag",
        "stepup_modifier": STEPUP_MODIFIER,
        "changed_trade_count": int(changed.sum()),
        "changed_selector_count": int((changed & masks["selector"]).sum()),
        "changed_holdout_count": int((changed & masks["holdout"]).sum()),
        "flag_trade_count": int(flag.sum()),
        "flag_selector_count": int((flag & masks["selector"]).sum()),
        "flag_holdout_count": int((flag & masks["holdout"]).sum()),
        "baseline_trade_count": int(len(baseline_path)),
    }
    for period, mask in masks.items():
        metrics = v144.v143._account_metrics(
            f"v160_{period}",
            candidate_path.loc[mask].copy(),
            return_col="v160_account_return_pct",
            pnl_col="v160_account_pnl_bps",
            baseline_months=baseline_months[period],
        )
        base = baseline_metrics[period]
        row[f"{period}_trade_count"] = metrics["trade_count"]
        row[f"{period}_return_pct"] = metrics["total_account_return_pct"]
        row[f"{period}_delta_return_pct"] = (
            float(metrics["total_account_return_pct"]) - float(base["total_account_return_pct"])
        )
        row[f"{period}_max_drawdown_pct"] = metrics["max_drawdown_pct"]
        row[f"{period}_delta_drawdown_pct"] = (
            float(metrics["max_drawdown_pct"]) - float(base["max_drawdown_pct"])
        )
        row[f"{period}_worst_month_pct"] = metrics["worst_month_pct"]
        row[f"{period}_delta_worst_month_pct"] = (
            float(metrics["worst_month_pct"]) - float(base["worst_month_pct"])
        )
        row[f"{period}_positive_months"] = metrics["positive_months"]
        row[f"{period}_month_count"] = metrics["month_count"]
        row[f"{period}_win_rate"] = metrics["win_rate"]
    return row


def _passes_v160_gate(candidate: dict[str, object], baseline: dict[str, dict[str, object]]) -> bool:
    if not candidate:
        return False
    return (
        int(candidate["changed_selector_count"]) >= MIN_CHANGED_SELECTOR_TRADES
        and int(candidate["changed_holdout_count"]) >= MIN_CHANGED_HOLDOUT_TRADES
        and float(candidate["full_return_pct"])
        >= float(baseline["full"]["total_account_return_pct"]) * MIN_INCREMENTAL_IMPROVEMENT_RATE
        and float(candidate["full_max_drawdown_pct"]) >= float(baseline["full"]["max_drawdown_pct"])
        and float(candidate["full_worst_month_pct"]) >= float(baseline["full"]["worst_month_pct"])
        and int(candidate["full_positive_months"]) == int(candidate["full_month_count"])
        and float(candidate["selector_return_pct"]) > float(baseline["selector"]["total_account_return_pct"])
        and float(candidate["selector_max_drawdown_pct"]) >= float(baseline["selector"]["max_drawdown_pct"])
        and float(candidate["selector_worst_month_pct"]) >= float(baseline["selector"]["worst_month_pct"])
        and int(candidate["selector_positive_months"]) == int(candidate["selector_month_count"])
        and float(candidate["holdout_return_pct"]) > float(baseline["holdout"]["total_account_return_pct"])
        and float(candidate["holdout_max_drawdown_pct"]) >= float(baseline["holdout"]["max_drawdown_pct"])
        and float(candidate["holdout_worst_month_pct"]) >= float(baseline["holdout"]["worst_month_pct"])
        and int(candidate["holdout_positive_months"]) == int(candidate["holdout_month_count"])
    )


def _context_metrics(frame: pd.DataFrame, candidate_path: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["v160_bucket"] = "unchanged"
    out.loc[candidate_path["v160_base_trend_abs_stepup_flag"], "v160_bucket"] = "base_trend_abs_stepup"
    out["win"] = pd.to_numeric(out["v159_account_return_pct"], errors="coerce") > 0.0
    grouped = (
        out.groupby("v160_bucket", observed=False)
        .agg(
            trade_count=("v159_account_return_pct", "size"),
            v159_account_return_pct=("v159_account_return_pct", "sum"),
            win_rate=("win", "mean"),
            avg_trend_abs_1440_bps=("trend_abs_1440_bps", "mean"),
            avg_prior_ret_1440_bps=("prior_ret_1440_bps", "mean"),
            avg_range_align_1440=("range_align_1440", "mean"),
            avg_premium_abs_bps=("premium_abs_bps", "mean"),
        )
        .reset_index()
    )
    grouped["win_rate"] = grouped["win_rate"] * 100.0
    return grouped


def _write_report(
    payload: dict[str, object],
    baseline_table: pd.DataFrame,
    context_table: pd.DataFrame,
    selected_monthly: pd.DataFrame,
) -> None:
    candidate = payload["selected_candidate"]
    decision = payload["decision"]
    lines = [
        "# Research V160 BTCUSDC Base Trend Abs Stepup",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to next model: `{decision['promote_to_v161']}`",
        f"- Message: {decision['message']}",
        f"- Selector period: `< {SELECTOR_END.isoformat()}`",
        f"- Holdout period: `>= {SELECTOR_END.isoformat()}`",
        "",
        "## Research Input",
        "",
        "- V160 tests whether the already-promoted V159 base trend-abs zone can tolerate a small additional sizing step.",
        f"- Stepup: trades with `v159_base_trend_abs_boost_flag` use an additional `{STEPUP_MODIFIER}x` sizing on top of V159.",
        "- The overlay does not add trades, change sides, or set a new threshold.",
        "",
        "## Baseline",
        "",
        baseline_table.to_csv(index=False).strip(),
        "",
        "## V160 Context Metrics",
        "",
        context_table.to_csv(index=False).strip(),
        "",
        "## Selected Candidate",
        "",
    ]
    lines.extend(pd.DataFrame([candidate]).to_csv(index=False).strip().splitlines())
    lines.extend(
        [
            "",
            "## Selected Monthly Account Return",
            "",
            selected_monthly.to_csv(index=False).strip(),
            "",
            "## Interpretation",
            "",
            "V160 suggests that the V159 base trend-abs flag can tolerate a small additional step-up. This is not a new signal; it is a narrow sizing adjustment on an already-locked flag.",
            "",
            "This is a research audit, not a live trading guarantee.",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not V159_ACCOUNT_PATH.exists():
        v159.run()
    frame = pd.read_csv(V159_ACCOUNT_PATH)
    frame["timestamp"] = _to_utc(frame["timestamp"])
    for column in ("v159_account_return_pct", "v159_account_pnl_bps"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    masks = _period_masks(frame)
    baseline, months = _baseline_metrics(frame, masks)
    selected_path = _apply_stepup(frame)
    selected = _candidate_metrics(
        frame,
        selected_path,
        masks=masks,
        baseline_metrics=baseline,
        baseline_months=months,
    )
    passed = _passes_v160_gate(selected, baseline)
    decision = {
        "status": "base_trend_abs_stepup_passed" if passed else "base_trend_abs_stepup_not_promoted",
        "promote_to_v161": bool(passed),
        "message": (
            "Base trend-abs stepup improved V159 by at least 1% without worsening selector/full/holdout risk gates."
            if passed
            else "Base trend-abs stepup did not clear the promotion gate."
        ),
    }
    payload = {
        "config": {
            "base": "v159_base_trend_abs_boost",
            "selector_end": SELECTOR_END.isoformat(),
            "min_incremental_improvement_rate": MIN_INCREMENTAL_IMPROVEMENT_RATE,
            "min_changed_selector_trades": MIN_CHANGED_SELECTOR_TRADES,
            "min_changed_holdout_trades": MIN_CHANGED_HOLDOUT_TRADES,
            "uses_holdout_for_thresholds": False,
            "adds_new_trades": False,
            "changes_existing_threshold": False,
        },
        "baseline": baseline,
        "selected_candidate": selected,
        "decision": decision,
    }
    selected_path.to_csv(OUT_DIR / "v160_selected_account_path.csv", index=False)
    pd.DataFrame([selected]).to_csv(OUT_DIR / "v160_base_trend_abs_stepup_candidate.csv", index=False)
    selected_monthly = (
        selected_path.assign(month=selected_path["timestamp"].dt.strftime("%Y-%m"))
        .groupby("month", sort=True)["v160_account_return_pct"]
        .sum()
        .reset_index()
        .rename(columns={"v160_account_return_pct": "account_return_pct"})
    )
    selected_monthly.to_csv(OUT_DIR / "v160_monthly_account_return.csv", index=False)
    context_table = _context_metrics(frame, selected_path)
    context_table.to_csv(OUT_DIR / "v160_base_trend_abs_context_metrics.csv", index=False)
    (OUT_DIR / "v160_base_trend_abs_stepup_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, pd.DataFrame(baseline.values()), context_table, selected_monthly)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
