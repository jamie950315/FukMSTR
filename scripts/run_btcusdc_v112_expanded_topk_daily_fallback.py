from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_btcusdc_v94_high_frequency_scan as v94
import run_btcusdc_v96_ml_probability_gate as v96
import run_btcusdc_v106_exact_daily_coverage_classifier as v106
import run_btcusdc_v111_high_confidence_daily_fallback as v111


OUT_DIR = ROOT / "runs" / "research_v112_btcusdc_expanded_topk_daily_fallback"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V112_BTCUSDC_EXPANDED_TOPK_DAILY_FALLBACK_RESULTS.md"
V111_SELECTED_PATH = v111.OUT_DIR / "v111_selector_locked_selected_candidate.csv"

FEATURE_FAMILIES = v111.FEATURE_FAMILIES
HORIZONS = v106.HORIZONS
PRIMARY_PROBABILITY_FLOORS = (1.0 / 3.0, 0.34, 0.35, 0.38, 0.40, 0.42, 0.45, 0.48, 0.50)
DAILY_TOP_KS = (5, 6, 7, 8, 9, 10)
FALLBACK_MIN_DAILY_TRADES = (1, 2, 3)
FEE_BPS = v111.FEE_BPS
MIN_RELATIVE_HOLDOUT_IMPROVEMENT = 0.05


def _meets_five_percent_target(current_holdout_bps: float, baseline_holdout_bps: float) -> bool:
    if float(baseline_holdout_bps) <= 0.0:
        return False
    return float(current_holdout_bps) >= float(baseline_holdout_bps) * (1.0 + MIN_RELATIVE_HOLDOUT_IMPROVEMENT)


def _passes_v112_selector_gate(row: dict[str, object]) -> bool:
    return (
        float(row["selector_total_net_pnl_bps"]) > 0.0
        and float(row["selector_win_rate"]) > v106.MIN_WIN_RATE
        and float(row["selector_avg_trades_per_calendar_day"]) >= v106.MIN_AVG_TRADES_PER_CALENDAR_DAY
        and float(row["selector_calendar_positive_month_rate"]) >= v106.MIN_CALENDAR_POSITIVE_MONTH_RATE
        and v106._has_exact_daily_coverage(row, "selector")
    )


def _selector_locked_v112_decision(
    candidates: pd.DataFrame,
    *,
    baseline_holdout_bps: float | None = None,
) -> dict[str, object]:
    if candidates.empty:
        return {
            "selector_exact_daily_candidate_count": 0,
            "selected_policy": None,
            "selector_locked_holdout_passed": False,
            "goal_satisfied_by_selector_locked_exact_daily_selection": False,
            "failed_reason": "no candidates available",
        }

    selector_mask = candidates.apply(lambda row: _passes_v112_selector_gate(row.to_dict()), axis=1)
    selector_candidates = candidates.loc[selector_mask].copy()
    if selector_candidates.empty:
        return {
            "selector_exact_daily_candidate_count": 0,
            "selected_policy": None,
            "selector_locked_holdout_passed": False,
            "goal_satisfied_by_selector_locked_exact_daily_selection": False,
            "failed_reason": "no candidate passed selector exact-daily fallback gate",
        }

    selected = selector_candidates.sort_values(
        [
            "selector_total_net_pnl_bps",
            "selector_win_rate",
            "selector_calendar_positive_month_rate",
            "selector_avg_trades_per_calendar_day",
        ],
        ascending=[False, False, False, False],
    ).iloc[0]
    selected_dict = selected.to_dict()
    holdout_passed = bool(v106._passes_exact_daily_gate(selected_dict))
    five_percent_target_met = (
        _meets_five_percent_target(float(selected_dict["holdout_total_net_pnl_bps"]), float(baseline_holdout_bps))
        if baseline_holdout_bps is not None
        else False
    )
    goal_satisfied = bool(holdout_passed and five_percent_target_met)
    failed_reason = None
    if not holdout_passed:
        failed_reason = "selector-locked fallback candidate failed holdout exact-daily gate"
    elif baseline_holdout_bps is not None and not five_percent_target_met:
        failed_reason = "selector-locked fallback candidate did not improve V111 holdout by at least 5%"
    return {
        "selector_exact_daily_candidate_count": int(len(selector_candidates)),
        "selected_policy": str(selected_dict["policy_id"]),
        "selector_locked_holdout_passed": holdout_passed,
        "five_percent_target_met": five_percent_target_met,
        "goal_satisfied_by_selector_locked_exact_daily_selection": goal_satisfied,
        "failed_reason": failed_reason,
    }


def _evaluate_horizon(bars: pd.DataFrame, *, horizon: int) -> tuple[list[dict[str, object]], dict[str, pd.DataFrame], dict[str, object]]:
    selector_pred, holdout_pred, family_metas = v111._ensemble_predictions(bars, horizon=int(horizon))
    if selector_pred.empty or holdout_pred.empty:
        return [], {}, {"horizon_minutes": int(horizon), "skipped": True, "reason": "empty ensemble predictions"}

    selector_start_ts = pd.to_datetime(selector_pred["timestamp"].min(), utc=True)
    selector_end_ts = pd.to_datetime(selector_pred["timestamp"].max(), utc=True)
    holdout_start_ts = pd.to_datetime(holdout_pred["timestamp"].min(), utc=True)
    holdout_end_ts = pd.to_datetime(holdout_pred["timestamp"].max(), utc=True)
    rows: list[dict[str, object]] = []
    ledgers: dict[str, pd.DataFrame] = {}

    for primary_floor in PRIMARY_PROBABILITY_FLOORS:
        for daily_top_k in DAILY_TOP_KS:
            for fallback_min in FALLBACK_MIN_DAILY_TRADES:
                if int(fallback_min) > int(daily_top_k):
                    continue
                selector_ledger = v111._daily_topk_probability_ledger_with_fallback(
                    selector_pred,
                    daily_top_k=int(daily_top_k),
                    primary_probability_floor=float(primary_floor),
                    fallback_min_daily_trades=int(fallback_min),
                    horizon_minutes=int(horizon),
                    fee_bps=FEE_BPS,
                )
                holdout_ledger = v111._daily_topk_probability_ledger_with_fallback(
                    holdout_pred,
                    daily_top_k=int(daily_top_k),
                    primary_probability_floor=float(primary_floor),
                    fallback_min_daily_trades=int(fallback_min),
                    horizon_minutes=int(horizon),
                    fee_bps=FEE_BPS,
                )
                selector_summary = v94._trade_summary(selector_ledger, start_ts=selector_start_ts, end_ts=selector_end_ts)
                holdout_summary = v94._trade_summary(holdout_ledger, start_ts=holdout_start_ts, end_ts=holdout_end_ts)
                selector_fallback_count = int(selector_ledger["used_fallback"].sum()) if "used_fallback" in selector_ledger else 0
                holdout_fallback_count = int(holdout_ledger["used_fallback"].sum()) if "used_fallback" in holdout_ledger else 0
                row = {
                    "policy_id": (
                        f"hgb_v112_expanded_topk_fallback_top{int(daily_top_k)}_h{int(horizon)}"
                        f"_p{float(primary_floor):.6f}_fb{int(fallback_min)}"
                    ),
                    "horizon_minutes": int(horizon),
                    "daily_top_k": int(daily_top_k),
                    "primary_probability_floor": float(primary_floor),
                    "fallback_min_daily_trades": int(fallback_min),
                    "fee_bps": float(FEE_BPS),
                    "feature_families": "+".join(FEATURE_FAMILIES),
                    "selector_fallback_trade_count": selector_fallback_count,
                    "holdout_fallback_trade_count": holdout_fallback_count,
                    **{f"selector_{key}": value for key, value in selector_summary.items()},
                    **{f"holdout_{key}": value for key, value in holdout_summary.items()},
                }
                row["passed_exact_daily_gate"] = bool(v106._passes_exact_daily_gate(row))
                rows.append(row)
                if bool(row["passed_exact_daily_gate"]):
                    ledgers[str(row["policy_id"])] = pd.concat(
                        [selector_ledger.assign(window="selector"), holdout_ledger.assign(window="holdout")],
                        ignore_index=True,
                    )

    meta = {
        "horizon_minutes": int(horizon),
        "feature_families": list(FEATURE_FAMILIES),
        "family_meta": family_metas,
        "selector_start_timestamp": selector_start_ts.isoformat(),
        "holdout_start_timestamp": holdout_start_ts.isoformat(),
        "holdout_end_timestamp": holdout_end_ts.isoformat(),
    }
    return rows, ledgers, meta


def _scan(bars: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    ledgers: dict[str, pd.DataFrame] = {}
    metas: list[dict[str, object]] = []
    for horizon in HORIZONS:
        horizon_rows, horizon_ledgers, meta = _evaluate_horizon(bars, horizon=int(horizon))
        rows.extend(horizon_rows)
        ledgers.update(horizon_ledgers)
        metas.append(meta)
        print(f"evaluated V112 expanded-topk fallback horizon {horizon} with {len(horizon_rows)} policies", flush=True)
    candidates = pd.DataFrame(rows)
    if not candidates.empty:
        candidates = candidates.sort_values(
            [
                "passed_exact_daily_gate",
                "selector_total_net_pnl_bps",
                "selector_win_rate",
                "holdout_total_net_pnl_bps",
            ],
            ascending=[False, False, False, False],
        ).reset_index(drop=True)
    return candidates, ledgers, metas


def _v111_baseline() -> dict[str, object]:
    if not V111_SELECTED_PATH.exists():
        return {"available": False}
    selected = pd.read_csv(V111_SELECTED_PATH)
    if selected.empty:
        return {"available": False}
    row = selected.iloc[0]
    holdout_bps = float(row["holdout_total_net_pnl_bps"])
    return {
        "available": True,
        "policy_id": str(row["policy_id"]),
        "holdout_total_net_pnl_bps": holdout_bps,
        "target_holdout_total_net_pnl_bps": holdout_bps * (1.0 + MIN_RELATIVE_HOLDOUT_IMPROVEMENT),
        "selector_total_net_pnl_bps": float(row["selector_total_net_pnl_bps"]),
        "holdout_win_rate": float(row["holdout_win_rate"]),
        "holdout_max_drawdown_bps": float(row["holdout_max_drawdown_bps"]),
    }


def _comparison_against_v111(selected_row: pd.DataFrame, baseline: dict[str, object]) -> dict[str, object]:
    if selected_row.empty or not baseline.get("available"):
        return {"available": False}
    current = selected_row.iloc[0]
    baseline_holdout = float(baseline["holdout_total_net_pnl_bps"])
    holdout_delta = float(current["holdout_total_net_pnl_bps"] - baseline_holdout)
    relative_delta = holdout_delta / baseline_holdout if baseline_holdout else 0.0
    return {
        "available": True,
        "v111_policy_id": str(baseline["policy_id"]),
        "v112_policy_id": str(current["policy_id"]),
        "target_holdout_total_net_pnl_bps": float(baseline["target_holdout_total_net_pnl_bps"]),
        "selector_total_net_pnl_bps_delta": float(
            current["selector_total_net_pnl_bps"] - float(baseline["selector_total_net_pnl_bps"])
        ),
        "holdout_total_net_pnl_bps_delta": holdout_delta,
        "holdout_total_net_pnl_relative_delta": relative_delta,
        "holdout_win_rate_delta": float(current["holdout_win_rate"] - float(baseline["holdout_win_rate"])),
        "holdout_max_drawdown_bps_delta": float(current["holdout_max_drawdown_bps"] - float(baseline["holdout_max_drawdown_bps"])),
    }


def _promotion_decision(selected_row: pd.DataFrame, comparison: dict[str, object]) -> dict[str, object]:
    if selected_row.empty:
        return {"promote_over_v111": False, "reason": "no selector-locked candidate"}
    if not comparison.get("available"):
        return {"promote_over_v111": False, "reason": "V111 comparison unavailable"}
    current = selected_row.iloc[0]
    if bool(current["passed_exact_daily_gate"]) and _meets_five_percent_target(
        float(current["holdout_total_net_pnl_bps"]),
        float(current["holdout_total_net_pnl_bps"] - comparison["holdout_total_net_pnl_bps_delta"]),
    ):
        pct = float(comparison["holdout_total_net_pnl_relative_delta"]) * 100.0
        return {"promote_over_v111": True, "reason": f"holdout PnL improved by {pct:.2f}% versus V111"}
    return {"promote_over_v111": False, "reason": "no selector-locked exact-daily candidate improved V111 by at least 5%"}


def _write_report(
    payload: dict[str, object],
    candidates: pd.DataFrame,
    selected_row: pd.DataFrame,
    passed: pd.DataFrame,
    comparison: dict[str, object],
    baseline: dict[str, object],
) -> None:
    report_cols = [
        "policy_id",
        "passed_exact_daily_gate",
        "horizon_minutes",
        "daily_top_k",
        "primary_probability_floor",
        "fallback_min_daily_trades",
        "selector_fallback_trade_count",
        "selector_trade_count",
        "selector_active_day_count",
        "selector_calendar_day_count",
        "selector_avg_trades_per_calendar_day",
        "selector_total_net_pnl_bps",
        "selector_win_rate",
        "selector_max_drawdown_bps",
        "selector_calendar_positive_month_rate",
        "holdout_fallback_trade_count",
        "holdout_trade_count",
        "holdout_active_day_count",
        "holdout_calendar_day_count",
        "holdout_avg_trades_per_calendar_day",
        "holdout_total_net_pnl_bps",
        "holdout_win_rate",
        "holdout_max_drawdown_bps",
        "holdout_calendar_positive_month_rate",
        "holdout_worst_month_net_pnl_bps",
    ]
    top = candidates.head(16).copy() if not candidates.empty else pd.DataFrame()
    target_lines = ["V111 baseline unavailable."]
    if baseline.get("available"):
        target_lines = [
            f"- V111 policy: `{baseline['policy_id']}`",
            f"- V111 holdout PnL: `{baseline['holdout_total_net_pnl_bps']:.6f}` bps",
            f"- Required +5% holdout target: `{baseline['target_holdout_total_net_pnl_bps']:.6f}` bps",
        ]
    comparison_lines = ["Comparison unavailable."]
    if comparison.get("available"):
        comparison_lines = [
            f"- V111 policy: `{comparison['v111_policy_id']}`",
            f"- V112 policy: `{comparison['v112_policy_id']}`",
            f"- Selector PnL delta: `{comparison['selector_total_net_pnl_bps_delta']:.6f}` bps",
            f"- Holdout PnL delta: `{comparison['holdout_total_net_pnl_bps_delta']:.6f}` bps",
            f"- Holdout relative delta: `{comparison['holdout_total_net_pnl_relative_delta']:.6f}`",
            f"- Holdout win-rate delta: `{comparison['holdout_win_rate_delta']:.6f}`",
            f"- Holdout max-drawdown delta: `{comparison['holdout_max_drawdown_bps_delta']:.6f}` bps",
        ]
    lines = [
        "# Research V112 BTCUSDC Expanded Top-K Daily Fallback Results",
        "",
        "## Decision",
        "",
        f"- Evaluated candidates: `{payload['scan']['candidate_count']}`",
        f"- Passing exact-daily candidates: `{payload['decision']['passing_candidate_count']}`",
        f"- Selector-locked selected candidate: `{payload['decision']['selected_policy']}`",
        f"- Holdout passed after selector lock: `{payload['decision']['selector_locked_holdout_passed']}`",
        f"- Five percent target met: `{payload['decision']['five_percent_target_met']}`",
        f"- Goal satisfied by strict exact-daily selection: `{payload['decision']['goal_satisfied_by_selector_locked_exact_daily_selection']}`",
        f"- Promote over V111: `{payload['decision']['promote_over_v111']}`",
        f"- Promotion reason: `{payload['decision']['promotion_reason']}`",
        "",
        "## V111 Target",
        "",
        *target_lines,
        "",
        "## Selected Candidate",
        "",
        selected_row[report_cols].to_csv(index=False).strip() if not selected_row.empty else "No selector-locked exact-daily candidate.",
        "",
        "## V111 Comparison",
        "",
        *comparison_lines,
        "",
        "## Top Candidates",
        "",
        top[report_cols].to_csv(index=False).strip() if not top.empty else "No candidates were produced.",
        "",
        "## Passing Candidates",
        "",
        passed[report_cols].to_csv(index=False).strip() if not passed.empty else "No candidate passed the exact-daily gate.",
        "",
        "## Interpretation",
        "",
        "V112 keeps the V111 ensemble and fallback design, then expands the selector-only daily top-k search from the old maximum of 5 to 10. The selected policy is still chosen only by selector-window quality; holdout is used only to validate the locked choice and to check the requested 5% improvement target. This remains a research candidate, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    bars = v94._full_bars()
    candidates, ledgers, metas = _scan(bars)
    passed = candidates.loc[candidates["passed_exact_daily_gate"]].copy() if not candidates.empty else pd.DataFrame()
    baseline = _v111_baseline()
    baseline_holdout = float(baseline["holdout_total_net_pnl_bps"]) if baseline.get("available") else None
    decision = _selector_locked_v112_decision(candidates, baseline_holdout_bps=baseline_holdout)
    selected_policy = decision["selected_policy"]
    selected_row = candidates.loc[candidates["policy_id"] == selected_policy].copy() if selected_policy is not None else pd.DataFrame()
    comparison = _comparison_against_v111(selected_row, baseline)
    promotion = _promotion_decision(selected_row, comparison)

    candidates_path = OUT_DIR / "v112_expanded_topk_daily_fallback_candidates.csv"
    passed_path = OUT_DIR / "v112_expanded_topk_daily_fallback_passed_candidates.csv"
    selected_path = OUT_DIR / "v112_selector_locked_selected_candidate.csv"
    candidates.to_csv(candidates_path, index=False)
    passed.to_csv(passed_path, index=False)
    selected_row.to_csv(selected_path, index=False)
    for policy_id, ledger in ledgers.items():
        ledger.to_csv(OUT_DIR / f"v112_{policy_id}_trade_ledger.csv", index=False)

    payload = {
        "version": "v112_btcusdc_expanded_topk_daily_fallback",
        "scan": {
            "candidate_count": int(len(candidates)),
            "horizons": list(HORIZONS),
            "daily_top_ks": list(DAILY_TOP_KS),
            "primary_probability_floors": list(PRIMARY_PROBABILITY_FLOORS),
            "fallback_min_daily_trades": list(FALLBACK_MIN_DAILY_TRADES),
            "fee_bps": float(FEE_BPS),
            "feature_families": list(FEATURE_FAMILIES),
            "sample_every_minutes": v96.SAMPLE_EVERY_MINUTES,
            "selector_days": v96.SELECTOR_DAYS,
            "holdout_days": v96.HOLDOUT_DAYS,
            "horizon_meta": metas,
        },
        "decision": {
            "passing_candidate_count": int(len(passed)),
            **decision,
            "promote_over_v111": bool(promotion["promote_over_v111"]),
            "promotion_reason": str(promotion["reason"]),
        },
        "baseline_v111": baseline,
        "comparison_against_v111": comparison,
        "outputs": {
            "candidates": str(candidates_path),
            "passed_candidates": str(passed_path),
            "selected_candidate": str(selected_path),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v112_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload, candidates, selected_row, passed, comparison, baseline)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
