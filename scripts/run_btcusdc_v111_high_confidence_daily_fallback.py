from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_btcusdc_v94_high_frequency_scan as v94
import run_btcusdc_v96_ml_probability_gate as v96
import run_btcusdc_v104_ma_hgb_daily_topk_classifier as v104
import run_btcusdc_v106_exact_daily_coverage_classifier as v106
import run_btcusdc_v109_feature_family_ensemble_exact_daily as v109


OUT_DIR = ROOT / "runs" / "research_v111_btcusdc_high_confidence_daily_fallback"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V111_BTCUSDC_HIGH_CONFIDENCE_DAILY_FALLBACK_RESULTS.md"
V109_SELECTED_PATH = v109.OUT_DIR / "v109_selector_locked_selected_candidate.csv"

FEATURE_FAMILIES = v109.FEATURE_FAMILIES
HORIZONS = v106.HORIZONS
PRIMARY_PROBABILITY_FLOORS = (1.0 / 3.0, 0.34, 0.35, 0.40, 0.45, 0.50)
DAILY_TOP_KS = (2, 3, 4, 5)
FALLBACK_MIN_DAILY_TRADES = (1, 2)
FEE_BPS = v106.FEE_BPS


def _empty_fallback_ledger() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "timestamp",
            "signal",
            "future_return_bps",
            "prob_down",
            "prob_flat",
            "prob_up",
            "direction_probability",
            "gross_pnl_bps",
            "net_pnl_bps",
            "daily_top_k",
            "primary_probability_floor",
            "fallback_min_daily_trades",
            "used_fallback",
            "horizon_minutes",
        ]
    )


def _select_non_overlapping_indices(
    ranked: pd.DataFrame,
    *,
    selected: list[int],
    selected_ts: list[pd.Timestamp],
    limit: int,
    horizon_minutes: int,
) -> tuple[list[int], list[pd.Timestamp]]:
    spacing = pd.Timedelta(minutes=int(horizon_minutes))
    for idx, row in ranked.iterrows():
        if len(selected) >= int(limit):
            break
        if int(idx) in selected:
            continue
        ts = pd.to_datetime(row["timestamp"], utc=True)
        if any(abs(ts - prev) < spacing for prev in selected_ts):
            continue
        selected.append(int(idx))
        selected_ts.append(ts)
    return selected, selected_ts


def _daily_topk_probability_ledger_with_fallback(
    predictions: pd.DataFrame,
    *,
    daily_top_k: int,
    primary_probability_floor: float,
    fallback_min_daily_trades: int,
    horizon_minutes: int,
    fee_bps: float,
) -> pd.DataFrame:
    frame = predictions.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    for column in ("future_return_bps", "prob_down", "prob_flat", "prob_up"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "future_return_bps", "prob_down", "prob_up"]).copy()
    frame["direction_probability"] = frame[["prob_up", "prob_down"]].max(axis=1)
    frame["signal"] = np.where(frame["prob_up"] >= frame["prob_down"], 1, -1).astype(int)
    if frame.empty:
        return _empty_fallback_ledger()

    keep_idx: list[int] = []
    fallback_idx: set[int] = set()
    for _, day_frame in frame.groupby(frame["timestamp"].dt.normalize(), sort=True):
        ranked_all = day_frame.sort_values(["direction_probability", "timestamp"], ascending=[False, True])
        ranked_primary = ranked_all.loc[ranked_all["direction_probability"] >= float(primary_probability_floor)]
        selected: list[int] = []
        selected_ts: list[pd.Timestamp] = []
        selected, selected_ts = _select_non_overlapping_indices(
            ranked_primary,
            selected=selected,
            selected_ts=selected_ts,
            limit=int(daily_top_k),
            horizon_minutes=int(horizon_minutes),
        )
        primary_count = len(selected)
        if len(selected) < int(fallback_min_daily_trades):
            selected, selected_ts = _select_non_overlapping_indices(
                ranked_all,
                selected=selected,
                selected_ts=selected_ts,
                limit=int(fallback_min_daily_trades),
                horizon_minutes=int(horizon_minutes),
            )
            fallback_idx.update(selected[primary_count:])
        keep_idx.extend(selected)

    if not keep_idx:
        return _empty_fallback_ledger()

    kept = frame.loc[keep_idx].copy().sort_values("timestamp").reset_index()
    future = pd.to_numeric(kept["future_return_bps"], errors="coerce").fillna(0.0).to_numpy(float)
    signal = kept["signal"].astype(int).to_numpy()
    gross = future * signal
    ledger = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(kept["timestamp"], utc=True).to_numpy(),
            "signal": signal,
            "future_return_bps": future,
            "prob_down": pd.to_numeric(kept["prob_down"], errors="coerce").fillna(0.0).to_numpy(float),
            "prob_flat": pd.to_numeric(kept["prob_flat"], errors="coerce").fillna(0.0).to_numpy(float),
            "prob_up": pd.to_numeric(kept["prob_up"], errors="coerce").fillna(0.0).to_numpy(float),
            "direction_probability": pd.to_numeric(kept["direction_probability"], errors="coerce").fillna(0.0).to_numpy(float),
            "gross_pnl_bps": gross,
            "net_pnl_bps": gross - float(fee_bps),
            "daily_top_k": int(daily_top_k),
            "primary_probability_floor": float(primary_probability_floor),
            "fallback_min_daily_trades": int(fallback_min_daily_trades),
            "used_fallback": kept["index"].map(lambda idx: int(idx) in fallback_idx).to_numpy(bool),
            "horizon_minutes": int(horizon_minutes),
        }
    )
    ledger["equity_bps"] = pd.to_numeric(ledger["net_pnl_bps"], errors="coerce").fillna(0.0).cumsum()
    return ledger


def _passes_v111_selector_gate(row: dict[str, object]) -> bool:
    return (
        float(row["selector_total_net_pnl_bps"]) > 0.0
        and float(row["selector_win_rate"]) > v106.MIN_WIN_RATE
        and float(row["selector_avg_trades_per_calendar_day"]) >= v106.MIN_AVG_TRADES_PER_CALENDAR_DAY
        and float(row["selector_calendar_positive_month_rate"]) >= v106.MIN_CALENDAR_POSITIVE_MONTH_RATE
        and v106._has_exact_daily_coverage(row, "selector")
    )


def _selector_locked_v111_decision(candidates: pd.DataFrame) -> dict[str, object]:
    if candidates.empty:
        return {
            "selector_exact_daily_candidate_count": 0,
            "selected_policy": None,
            "selector_locked_holdout_passed": False,
            "goal_satisfied_by_selector_locked_exact_daily_selection": False,
            "failed_reason": "no candidates available",
        }

    selector_mask = candidates.apply(lambda row: _passes_v111_selector_gate(row.to_dict()), axis=1)
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
    return {
        "selector_exact_daily_candidate_count": int(len(selector_candidates)),
        "selected_policy": str(selected_dict["policy_id"]),
        "selector_locked_holdout_passed": holdout_passed,
        "goal_satisfied_by_selector_locked_exact_daily_selection": holdout_passed,
        "failed_reason": None if holdout_passed else "selector-locked fallback candidate failed holdout exact-daily gate",
    }


def _ensemble_predictions(bars: pd.DataFrame, *, horizon: int) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, object]]]:
    selector_frames: list[pd.DataFrame] = []
    holdout_frames: list[pd.DataFrame] = []
    family_metas: list[dict[str, object]] = []
    for family in FEATURE_FAMILIES:
        selector_pred, holdout_pred, family_meta = v109._family_predictions(bars, horizon=int(horizon), family=family)
        selector_frames.append(selector_pred)
        holdout_frames.append(holdout_pred)
        family_metas.append(family_meta)
    return v109._average_probability_frames(selector_frames), v109._average_probability_frames(holdout_frames), family_metas


def _evaluate_horizon(bars: pd.DataFrame, *, horizon: int) -> tuple[list[dict[str, object]], dict[str, pd.DataFrame], dict[str, object]]:
    selector_pred, holdout_pred, family_metas = _ensemble_predictions(bars, horizon=int(horizon))
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
                selector_ledger = _daily_topk_probability_ledger_with_fallback(
                    selector_pred,
                    daily_top_k=int(daily_top_k),
                    primary_probability_floor=float(primary_floor),
                    fallback_min_daily_trades=int(fallback_min),
                    horizon_minutes=int(horizon),
                    fee_bps=FEE_BPS,
                )
                holdout_ledger = _daily_topk_probability_ledger_with_fallback(
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
                        f"hgb_v111_highconf_fallback_top{int(daily_top_k)}_h{int(horizon)}"
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
        print(f"evaluated V111 high-confidence fallback horizon {horizon} with {len(horizon_rows)} policies", flush=True)
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


def _comparison_against_v109(selected_row: pd.DataFrame) -> dict[str, object]:
    if selected_row.empty or not V109_SELECTED_PATH.exists():
        return {"available": False}
    v109_selected = pd.read_csv(V109_SELECTED_PATH)
    if v109_selected.empty:
        return {"available": False}
    current = selected_row.iloc[0]
    baseline = v109_selected.iloc[0]
    return {
        "available": True,
        "v109_policy_id": str(baseline["policy_id"]),
        "v111_policy_id": str(current["policy_id"]),
        "selector_total_net_pnl_bps_delta": float(current["selector_total_net_pnl_bps"] - baseline["selector_total_net_pnl_bps"]),
        "selector_win_rate_delta": float(current["selector_win_rate"] - baseline["selector_win_rate"]),
        "selector_max_drawdown_bps_delta": float(current["selector_max_drawdown_bps"] - baseline["selector_max_drawdown_bps"]),
        "holdout_total_net_pnl_bps_delta": float(current["holdout_total_net_pnl_bps"] - baseline["holdout_total_net_pnl_bps"]),
        "holdout_win_rate_delta": float(current["holdout_win_rate"] - baseline["holdout_win_rate"]),
        "holdout_max_drawdown_bps_delta": float(current["holdout_max_drawdown_bps"] - baseline["holdout_max_drawdown_bps"]),
    }


def _promotion_decision(selected_row: pd.DataFrame, comparison: dict[str, object]) -> dict[str, object]:
    if selected_row.empty:
        return {"promote_over_v109": False, "reason": "no selector-locked candidate"}
    if not comparison.get("available"):
        return {"promote_over_v109": False, "reason": "V109 comparison unavailable"}
    holdout_pnl_delta = float(comparison["holdout_total_net_pnl_bps_delta"])
    drawdown_delta = float(comparison["holdout_max_drawdown_bps_delta"])
    current = selected_row.iloc[0]
    if bool(current["passed_exact_daily_gate"]) and holdout_pnl_delta >= 500.0:
        return {"promote_over_v109": True, "reason": "holdout PnL improved by at least 500 bps under exact-daily fallback"}
    if bool(current["passed_exact_daily_gate"]) and holdout_pnl_delta >= -250.0 and drawdown_delta <= -100.0:
        return {"promote_over_v109": True, "reason": "drawdown improved by at least 100 bps with close holdout PnL"}
    return {"promote_over_v109": False, "reason": "no material improvement versus V109"}


def _write_report(
    payload: dict[str, object],
    candidates: pd.DataFrame,
    selected_row: pd.DataFrame,
    passed: pd.DataFrame,
    comparison: dict[str, object],
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
    comparison_lines = ["Comparison unavailable."]
    if comparison.get("available"):
        comparison_lines = [
            f"- V109 policy: `{comparison['v109_policy_id']}`",
            f"- V111 policy: `{comparison['v111_policy_id']}`",
            f"- Selector PnL delta: `{comparison['selector_total_net_pnl_bps_delta']:.6f}` bps",
            f"- Selector win-rate delta: `{comparison['selector_win_rate_delta']:.6f}`",
            f"- Selector max-drawdown delta: `{comparison['selector_max_drawdown_bps_delta']:.6f}` bps",
            f"- Holdout PnL delta: `{comparison['holdout_total_net_pnl_bps_delta']:.6f}` bps",
            f"- Holdout win-rate delta: `{comparison['holdout_win_rate_delta']:.6f}`",
            f"- Holdout max-drawdown delta: `{comparison['holdout_max_drawdown_bps_delta']:.6f}` bps",
        ]
    lines = [
        "# Research V111 BTCUSDC High Confidence Daily Fallback Results",
        "",
        "## Decision",
        "",
        f"- Evaluated candidates: `{payload['scan']['candidate_count']}`",
        f"- Passing exact-daily candidates: `{payload['decision']['passing_candidate_count']}`",
        f"- Selector-locked selected candidate: `{payload['decision']['selected_policy']}`",
        f"- Holdout passed after selector lock: `{payload['decision']['selector_locked_holdout_passed']}`",
        f"- Goal satisfied by strict exact-daily selection: `{payload['decision']['goal_satisfied_by_selector_locked_exact_daily_selection']}`",
        f"- Promote over V109: `{payload['decision']['promote_over_v109']}`",
        f"- Promotion reason: `{payload['decision']['promotion_reason']}`",
        "",
        "## Selected Candidate",
        "",
        selected_row[report_cols].to_csv(index=False).strip() if not selected_row.empty else "No selector-locked exact-daily candidate.",
        "",
        "## V109 Comparison",
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
        "V111 keeps the V109 feature-family ensemble, prioritizes high-confidence predictions, and fills only the minimum required daily fallback trades so every calendar day remains active. This remains a research candidate, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    bars = v94._full_bars()
    candidates, ledgers, metas = _scan(bars)
    passed = candidates.loc[candidates["passed_exact_daily_gate"]].copy() if not candidates.empty else pd.DataFrame()
    decision = _selector_locked_v111_decision(candidates)
    selected_policy = decision["selected_policy"]
    selected_row = candidates.loc[candidates["policy_id"] == selected_policy].copy() if selected_policy is not None else pd.DataFrame()
    comparison = _comparison_against_v109(selected_row)
    promotion = _promotion_decision(selected_row, comparison)

    candidates_path = OUT_DIR / "v111_high_confidence_daily_fallback_candidates.csv"
    passed_path = OUT_DIR / "v111_high_confidence_daily_fallback_passed_candidates.csv"
    selected_path = OUT_DIR / "v111_selector_locked_selected_candidate.csv"
    candidates.to_csv(candidates_path, index=False)
    passed.to_csv(passed_path, index=False)
    selected_row.to_csv(selected_path, index=False)
    for policy_id, ledger in ledgers.items():
        ledger.to_csv(OUT_DIR / f"v111_{policy_id}_trade_ledger.csv", index=False)

    payload = {
        "version": "v111_btcusdc_high_confidence_daily_fallback",
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
            "promote_over_v109": bool(promotion["promote_over_v109"]),
            "promotion_reason": str(promotion["reason"]),
        },
        "comparison_against_v109": comparison,
        "outputs": {
            "candidates": str(candidates_path),
            "passed_candidates": str(passed_path),
            "selected_candidate": str(selected_path),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v111_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload, candidates, selected_row, passed, comparison)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
