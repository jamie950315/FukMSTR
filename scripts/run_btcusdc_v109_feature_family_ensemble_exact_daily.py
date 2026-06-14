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
import run_btcusdc_v102_ma_feature_regression as v102
import run_btcusdc_v104_ma_hgb_daily_topk_classifier as v104
import run_btcusdc_v106_exact_daily_coverage_classifier as v106
import run_btcusdc_v107_price_context_exact_daily_classifier as v107
import run_btcusdc_v108_technical_indicator_exact_daily_classifier as v108


OUT_DIR = ROOT / "runs" / "research_v109_btcusdc_feature_family_ensemble_exact_daily"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V109_BTCUSDC_FEATURE_FAMILY_ENSEMBLE_EXACT_DAILY_RESULTS.md"
V106_SELECTED_PATH = v106.OUT_DIR / "v106_selector_locked_selected_candidate.csv"

FEATURE_FAMILIES = ("ma", "price_context", "technical")
HORIZONS = v106.HORIZONS
PROBABILITY_FLOORS = v106.PROBABILITY_FLOORS
DAILY_TOP_KS = v106.DAILY_TOP_KS
FEE_BPS = v106.FEE_BPS


def _feature_frame_for_family(family: str, bars: pd.DataFrame, *, horizon_minutes: int) -> tuple[pd.DataFrame, list[str]]:
    if family == "ma":
        return v102._ma_feature_frame(bars, horizon_minutes=int(horizon_minutes))
    if family == "price_context":
        return v107._price_context_feature_frame(bars, horizon_minutes=int(horizon_minutes))
    if family == "technical":
        return v108._technical_indicator_feature_frame(bars, horizon_minutes=int(horizon_minutes))
    raise ValueError(f"unknown feature family: {family}")


def _average_probability_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame(columns=["timestamp", "future_return_bps", "prob_down", "prob_flat", "prob_up"])
    merged: pd.DataFrame | None = None
    for idx, frame in enumerate(frames):
        current = frame[["timestamp", "future_return_bps", "prob_down", "prob_flat", "prob_up"]].copy()
        current["timestamp"] = pd.to_datetime(current["timestamp"], utc=True)
        current = current.rename(
            columns={
                "future_return_bps": f"future_return_bps_{idx}",
                "prob_down": f"prob_down_{idx}",
                "prob_flat": f"prob_flat_{idx}",
                "prob_up": f"prob_up_{idx}",
            }
        )
        merged = current if merged is None else merged.merge(current, on="timestamp", how="inner")
    assert merged is not None
    out = pd.DataFrame({"timestamp": pd.to_datetime(merged["timestamp"], utc=True)})
    out["future_return_bps"] = pd.to_numeric(merged["future_return_bps_0"], errors="coerce")
    for column in ("prob_down", "prob_flat", "prob_up"):
        source_cols = [f"{column}_{idx}" for idx in range(len(frames))]
        out[column] = merged[source_cols].apply(pd.to_numeric, errors="coerce").mean(axis=1)
    return out.sort_values("timestamp").reset_index(drop=True)


def _family_predictions(
    bars: pd.DataFrame,
    *,
    horizon: int,
    family: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    data, feature_cols = _feature_frame_for_family(family, bars, horizon_minutes=int(horizon))
    full_end = pd.to_datetime(data["timestamp"].max(), utc=True)
    holdout_start = full_end - pd.Timedelta(days=v96.HOLDOUT_DAYS)
    selector_start = holdout_start - pd.Timedelta(days=v96.SELECTOR_DAYS)
    train = data.loc[data["timestamp"] < selector_start].copy()
    selector = data.loc[(data["timestamp"] >= selector_start) & (data["timestamp"] < holdout_start)].copy()
    holdout = data.loc[data["timestamp"] >= holdout_start].copy()
    model = v104._fit_hgb_classifier(train, feature_cols)
    selector_pred = v104._probability_predictions(model, selector, feature_cols)
    holdout_pred = v104._probability_predictions(model, holdout, feature_cols)
    meta = {
        "family": family,
        "horizon_minutes": int(horizon),
        "train_rows": int(len(train)),
        "selector_rows": int(len(selector)),
        "holdout_rows": int(len(holdout)),
        "feature_count": int(len(feature_cols)),
        "selector_start_timestamp": pd.to_datetime(selector["timestamp"].min(), utc=True).isoformat(),
        "selector_end_timestamp": pd.to_datetime(selector["timestamp"].max(), utc=True).isoformat(),
        "holdout_start_timestamp": pd.to_datetime(holdout["timestamp"].min(), utc=True).isoformat(),
        "holdout_end_timestamp": pd.to_datetime(holdout["timestamp"].max(), utc=True).isoformat(),
    }
    return selector_pred, holdout_pred, meta


def _evaluate_horizon(bars: pd.DataFrame, *, horizon: int) -> tuple[list[dict[str, object]], dict[str, pd.DataFrame], dict[str, object]]:
    selector_frames: list[pd.DataFrame] = []
    holdout_frames: list[pd.DataFrame] = []
    family_metas: list[dict[str, object]] = []
    for family in FEATURE_FAMILIES:
        selector_pred, holdout_pred, family_meta = _family_predictions(bars, horizon=int(horizon), family=family)
        selector_frames.append(selector_pred)
        holdout_frames.append(holdout_pred)
        family_metas.append(family_meta)

    selector_pred = _average_probability_frames(selector_frames)
    holdout_pred = _average_probability_frames(holdout_frames)
    if selector_pred.empty or holdout_pred.empty:
        return [], {}, {"horizon_minutes": int(horizon), "skipped": True, "reason": "empty ensemble predictions"}

    selector_start_ts = pd.to_datetime(selector_pred["timestamp"].min(), utc=True)
    selector_end_ts = pd.to_datetime(selector_pred["timestamp"].max(), utc=True)
    holdout_start_ts = pd.to_datetime(holdout_pred["timestamp"].min(), utc=True)
    holdout_end_ts = pd.to_datetime(holdout_pred["timestamp"].max(), utc=True)
    rows: list[dict[str, object]] = []
    ledgers: dict[str, pd.DataFrame] = {}

    for probability_floor in PROBABILITY_FLOORS:
        for daily_top_k in DAILY_TOP_KS:
            selector_ledger = v104._daily_topk_probability_ledger(
                selector_pred,
                daily_top_k=int(daily_top_k),
                probability_floor=float(probability_floor),
                horizon_minutes=int(horizon),
                fee_bps=FEE_BPS,
            )
            holdout_ledger = v104._daily_topk_probability_ledger(
                holdout_pred,
                daily_top_k=int(daily_top_k),
                probability_floor=float(probability_floor),
                horizon_minutes=int(horizon),
                fee_bps=FEE_BPS,
            )
            selector_summary = v94._trade_summary(selector_ledger, start_ts=selector_start_ts, end_ts=selector_end_ts)
            holdout_summary = v94._trade_summary(holdout_ledger, start_ts=holdout_start_ts, end_ts=holdout_end_ts)
            row = {
                "policy_id": f"hgb_feature_ensemble_exact_daily_top{int(daily_top_k)}_h{int(horizon)}_p{float(probability_floor):.6f}",
                "horizon_minutes": int(horizon),
                "daily_top_k": int(daily_top_k),
                "probability_floor": float(probability_floor),
                "fee_bps": float(FEE_BPS),
                "feature_families": "+".join(FEATURE_FAMILIES),
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
        print(f"evaluated feature-family ensemble exact-daily horizon {horizon} with {len(horizon_rows)} policies", flush=True)
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


def _comparison_against_v106(selected_row: pd.DataFrame) -> dict[str, object]:
    if selected_row.empty or not V106_SELECTED_PATH.exists():
        return {"available": False}
    v106_selected = pd.read_csv(V106_SELECTED_PATH)
    if v106_selected.empty:
        return {"available": False}
    current = selected_row.iloc[0]
    baseline = v106_selected.iloc[0]
    return {
        "available": True,
        "v106_policy_id": str(baseline["policy_id"]),
        "v109_policy_id": str(current["policy_id"]),
        "selector_total_net_pnl_bps_delta": float(current["selector_total_net_pnl_bps"] - baseline["selector_total_net_pnl_bps"]),
        "selector_win_rate_delta": float(current["selector_win_rate"] - baseline["selector_win_rate"]),
        "holdout_total_net_pnl_bps_delta": float(current["holdout_total_net_pnl_bps"] - baseline["holdout_total_net_pnl_bps"]),
        "holdout_win_rate_delta": float(current["holdout_win_rate"] - baseline["holdout_win_rate"]),
        "holdout_max_drawdown_bps_delta": float(current["holdout_max_drawdown_bps"] - baseline["holdout_max_drawdown_bps"]),
    }


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
        "probability_floor",
        "selector_trade_count",
        "selector_active_day_count",
        "selector_calendar_day_count",
        "selector_avg_trades_per_calendar_day",
        "selector_total_net_pnl_bps",
        "selector_win_rate",
        "selector_max_drawdown_bps",
        "selector_calendar_positive_month_rate",
        "holdout_trade_count",
        "holdout_active_day_count",
        "holdout_calendar_day_count",
        "holdout_avg_trades_per_calendar_day",
        "holdout_total_net_pnl_bps",
        "holdout_win_rate",
        "holdout_max_drawdown_bps",
        "holdout_calendar_positive_month_rate",
    ]
    top = candidates.head(12).copy() if not candidates.empty else pd.DataFrame()
    comparison_lines = ["Comparison unavailable."]
    if comparison.get("available"):
        comparison_lines = [
            f"- V106 policy: `{comparison['v106_policy_id']}`",
            f"- V109 policy: `{comparison['v109_policy_id']}`",
            f"- Selector PnL delta: `{comparison['selector_total_net_pnl_bps_delta']:.6f}` bps",
            f"- Selector win-rate delta: `{comparison['selector_win_rate_delta']:.6f}`",
            f"- Holdout PnL delta: `{comparison['holdout_total_net_pnl_bps_delta']:.6f}` bps",
            f"- Holdout win-rate delta: `{comparison['holdout_win_rate_delta']:.6f}`",
            f"- Holdout max-drawdown delta: `{comparison['holdout_max_drawdown_bps_delta']:.6f}` bps",
        ]
    lines = [
        "# Research V109 BTCUSDC Feature Family Ensemble Exact Daily Results",
        "",
        "## Decision",
        "",
        f"- Evaluated candidates: `{payload['scan']['candidate_count']}`",
        f"- Passing exact-daily candidates: `{payload['decision']['passing_candidate_count']}`",
        f"- Selector-locked selected candidate: `{payload['decision']['selected_policy']}`",
        f"- Holdout passed after selector lock: `{payload['decision']['selector_locked_holdout_passed']}`",
        f"- Goal satisfied by strict exact-daily selection: `{payload['decision']['goal_satisfied_by_selector_locked_exact_daily_selection']}`",
        f"- Feature families: `{list(FEATURE_FAMILIES)}`",
        "",
        "## Selected Candidate",
        "",
        selected_row[report_cols].to_csv(index=False).strip() if not selected_row.empty else "No selector-locked exact-daily candidate.",
        "",
        "## V106 Comparison",
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
        "V109 averages probability outputs from the MA-only, price-context, and technical-indicator HGB classifiers before applying the same V106 exact-daily execution gate. This remains a research candidate, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    bars = v94._full_bars()
    candidates, ledgers, metas = _scan(bars)
    passed = candidates.loc[candidates["passed_exact_daily_gate"]].copy() if not candidates.empty else pd.DataFrame()
    decision = v106._selector_locked_exact_daily_decision(candidates)
    selected_policy = decision["selected_policy"]
    selected_row = candidates.loc[candidates["policy_id"] == selected_policy].copy() if selected_policy is not None else pd.DataFrame()
    comparison = _comparison_against_v106(selected_row)

    candidates_path = OUT_DIR / "v109_feature_family_ensemble_candidates.csv"
    passed_path = OUT_DIR / "v109_feature_family_ensemble_passed_candidates.csv"
    selected_path = OUT_DIR / "v109_selector_locked_selected_candidate.csv"
    candidates.to_csv(candidates_path, index=False)
    passed.to_csv(passed_path, index=False)
    selected_row.to_csv(selected_path, index=False)
    for policy_id, ledger in ledgers.items():
        ledger.to_csv(OUT_DIR / f"v109_{policy_id}_trade_ledger.csv", index=False)

    payload = {
        "version": "v109_btcusdc_feature_family_ensemble_exact_daily",
        "scan": {
            "candidate_count": int(len(candidates)),
            "horizons": list(HORIZONS),
            "daily_top_ks": list(DAILY_TOP_KS),
            "probability_floors": list(PROBABILITY_FLOORS),
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
        },
        "comparison_against_v106": comparison,
        "outputs": {
            "candidates": str(candidates_path),
            "passed_candidates": str(passed_path),
            "selected_candidate": str(selected_path),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v109_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload, candidates, selected_row, passed, comparison)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
