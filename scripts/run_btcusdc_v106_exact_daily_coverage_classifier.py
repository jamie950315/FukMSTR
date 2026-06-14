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
import run_btcusdc_v101_thick_edge_regression as v101
import run_btcusdc_v102_ma_feature_regression as v102
import run_btcusdc_v104_ma_hgb_daily_topk_classifier as v104


OUT_DIR = ROOT / "runs" / "research_v106_btcusdc_exact_daily_coverage_classifier"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V106_BTCUSDC_EXACT_DAILY_COVERAGE_CLASSIFIER_RESULTS.md"

HORIZONS = (5, 10, 15, 30)
PROBABILITY_FLOORS = (0.0, 1.0 / 3.0, 0.34, 0.35, 0.40)
DAILY_TOP_KS = (1, 2, 3, 4, 5)
FEE_BPS = v101.FEE_BPS

MIN_WIN_RATE = v101.MIN_WIN_RATE
MIN_AVG_TRADES_PER_CALENDAR_DAY = v101.MIN_AVG_TRADES_PER_CALENDAR_DAY
MIN_CALENDAR_POSITIVE_MONTH_RATE = v101.MIN_CALENDAR_POSITIVE_MONTH_RATE


def _has_exact_daily_coverage(row: dict[str, object], prefix: str) -> bool:
    return int(row[f"{prefix}_active_day_count"]) == int(row[f"{prefix}_calendar_day_count"])


def _passes_exact_daily_gate(row: dict[str, object]) -> bool:
    return (
        float(row["selector_total_net_pnl_bps"]) > 0.0
        and float(row["holdout_total_net_pnl_bps"]) > 0.0
        and float(row["selector_win_rate"]) > MIN_WIN_RATE
        and float(row["holdout_win_rate"]) > MIN_WIN_RATE
        and float(row["selector_avg_trades_per_calendar_day"]) >= MIN_AVG_TRADES_PER_CALENDAR_DAY
        and float(row["holdout_avg_trades_per_calendar_day"]) >= MIN_AVG_TRADES_PER_CALENDAR_DAY
        and float(row["selector_calendar_positive_month_rate"]) >= MIN_CALENDAR_POSITIVE_MONTH_RATE
        and float(row["holdout_calendar_positive_month_rate"]) >= MIN_CALENDAR_POSITIVE_MONTH_RATE
        and _has_exact_daily_coverage(row, "selector")
        and _has_exact_daily_coverage(row, "holdout")
    )


def _passes_selector_exact_daily_gate(row: dict[str, object]) -> bool:
    if "probability_floor" in row and float(row["probability_floor"]) != 0.0:
        return False
    return (
        float(row["selector_total_net_pnl_bps"]) > 0.0
        and float(row["selector_win_rate"]) > MIN_WIN_RATE
        and float(row["selector_avg_trades_per_calendar_day"]) >= MIN_AVG_TRADES_PER_CALENDAR_DAY
        and float(row["selector_calendar_positive_month_rate"]) >= MIN_CALENDAR_POSITIVE_MONTH_RATE
        and _has_exact_daily_coverage(row, "selector")
    )


def _selector_locked_exact_daily_decision(candidates: pd.DataFrame) -> dict[str, object]:
    if candidates.empty:
        return {
            "selector_exact_daily_candidate_count": 0,
            "selected_policy": None,
            "selector_locked_holdout_passed": False,
            "goal_satisfied_by_selector_locked_exact_daily_selection": False,
            "failed_reason": "no candidates available",
        }

    selector_mask = candidates.apply(lambda row: _passes_selector_exact_daily_gate(row.to_dict()), axis=1)
    selector_candidates = candidates.loc[selector_mask].copy()
    if selector_candidates.empty:
        return {
            "selector_exact_daily_candidate_count": 0,
            "selected_policy": None,
            "selector_locked_holdout_passed": False,
            "goal_satisfied_by_selector_locked_exact_daily_selection": False,
            "failed_reason": "no candidate passed selector exact-daily gate",
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
    holdout_passed = bool(_passes_exact_daily_gate(selected_dict))
    return {
        "selector_exact_daily_candidate_count": int(len(selector_candidates)),
        "selected_policy": str(selected_dict["policy_id"]),
        "selector_locked_holdout_passed": holdout_passed,
        "goal_satisfied_by_selector_locked_exact_daily_selection": holdout_passed,
        "failed_reason": None if holdout_passed else "selector-locked exact-daily candidate failed holdout exact-daily gate",
    }


def _evaluate_horizon(bars: pd.DataFrame, *, horizon: int) -> tuple[list[dict[str, object]], dict[str, pd.DataFrame], dict[str, object]]:
    data, feature_cols = v102._ma_feature_frame(bars, horizon_minutes=int(horizon))
    full_end = pd.to_datetime(data["timestamp"].max(), utc=True)
    holdout_start = full_end - pd.Timedelta(days=v96.HOLDOUT_DAYS)
    selector_start = holdout_start - pd.Timedelta(days=v96.SELECTOR_DAYS)
    train = data.loc[data["timestamp"] < selector_start].copy()
    selector = data.loc[(data["timestamp"] >= selector_start) & (data["timestamp"] < holdout_start)].copy()
    holdout = data.loc[data["timestamp"] >= holdout_start].copy()
    if len(train) < 1000 or len(selector) < 100 or len(holdout) < 100:
        return [], {}, {"horizon_minutes": int(horizon), "skipped": True, "reason": "insufficient rows"}

    model = v104._fit_hgb_classifier(train, feature_cols)
    selector_pred = v104._probability_predictions(model, selector, feature_cols)
    holdout_pred = v104._probability_predictions(model, holdout, feature_cols)
    selector_start_ts = pd.to_datetime(selector["timestamp"].min(), utc=True)
    selector_end_ts = pd.to_datetime(selector["timestamp"].max(), utc=True)
    holdout_start_ts = pd.to_datetime(holdout["timestamp"].min(), utc=True)
    holdout_end_ts = pd.to_datetime(holdout["timestamp"].max(), utc=True)
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
                "policy_id": f"hgb_ma_exact_daily_top{int(daily_top_k)}_h{int(horizon)}_p{float(probability_floor):.6f}",
                "horizon_minutes": int(horizon),
                "daily_top_k": int(daily_top_k),
                "probability_floor": float(probability_floor),
                "fee_bps": float(FEE_BPS),
                "train_rows": int(len(train)),
                "selector_rows": int(len(selector)),
                "holdout_rows": int(len(holdout)),
                "feature_count": int(len(feature_cols)),
                **{f"selector_{key}": value for key, value in selector_summary.items()},
                **{f"holdout_{key}": value for key, value in holdout_summary.items()},
            }
            row["passed_exact_daily_gate"] = bool(_passes_exact_daily_gate(row))
            rows.append(row)
            if bool(row["passed_exact_daily_gate"]):
                ledgers[str(row["policy_id"])] = pd.concat(
                    [selector_ledger.assign(window="selector"), holdout_ledger.assign(window="holdout")],
                    ignore_index=True,
                )

    meta = {
        "horizon_minutes": int(horizon),
        "train_rows": int(len(train)),
        "selector_rows": int(len(selector)),
        "holdout_rows": int(len(holdout)),
        "feature_count": int(len(feature_cols)),
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
        print(f"evaluated exact-daily classifier horizon {horizon} with {len(horizon_rows)} policies", flush=True)
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


def _write_report(payload: dict[str, object], candidates: pd.DataFrame, selected_row: pd.DataFrame, passed: pd.DataFrame) -> None:
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
        "selector_calendar_positive_month_rate",
        "holdout_trade_count",
        "holdout_active_day_count",
        "holdout_calendar_day_count",
        "holdout_avg_trades_per_calendar_day",
        "holdout_total_net_pnl_bps",
        "holdout_win_rate",
        "holdout_calendar_positive_month_rate",
    ]
    top = candidates.head(12).copy() if not candidates.empty else pd.DataFrame()
    lines = [
        "# Research V106 BTCUSDC Exact Daily Coverage Classifier Results",
        "",
        "## Decision",
        "",
        f"- Evaluated candidates: `{payload['scan']['candidate_count']}`",
        f"- Passing exact-daily candidates: `{payload['decision']['passing_candidate_count']}`",
        f"- Selector-locked selected candidate: `{payload['decision']['selected_policy']}`",
        f"- Holdout passed after selector lock: `{payload['decision']['selector_locked_holdout_passed']}`",
        f"- Goal satisfied by strict exact-daily selection: `{payload['decision']['goal_satisfied_by_selector_locked_exact_daily_selection']}`",
        "",
        "## Selected Candidate",
        "",
        selected_row[report_cols].to_csv(index=False).strip() if not selected_row.empty else "No selector-locked exact-daily candidate.",
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
        "V106 tests the strict daily requirement by demanding at least one trade on every calendar day in both selector and holdout windows. Selection is locked using selector-window evidence only and requires probability floor 0.0 so daily participation is structural rather than dependent on future confidence distributions. This remains a research candidate, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    bars = v94._full_bars()
    candidates, ledgers, metas = _scan(bars)
    passed = candidates.loc[candidates["passed_exact_daily_gate"]].copy() if not candidates.empty else pd.DataFrame()
    decision = _selector_locked_exact_daily_decision(candidates)
    selected_policy = decision["selected_policy"]
    selected_row = candidates.loc[candidates["policy_id"] == selected_policy].copy() if selected_policy is not None else pd.DataFrame()

    candidates_path = OUT_DIR / "v106_exact_daily_candidates.csv"
    passed_path = OUT_DIR / "v106_exact_daily_passed_candidates.csv"
    selected_path = OUT_DIR / "v106_selector_locked_selected_candidate.csv"
    candidates.to_csv(candidates_path, index=False)
    passed.to_csv(passed_path, index=False)
    selected_row.to_csv(selected_path, index=False)
    for policy_id, ledger in ledgers.items():
        ledger.to_csv(OUT_DIR / f"v106_{policy_id}_trade_ledger.csv", index=False)

    payload = {
        "version": "v106_btcusdc_exact_daily_coverage_classifier",
        "scan": {
            "candidate_count": int(len(candidates)),
            "horizons": list(HORIZONS),
            "daily_top_ks": list(DAILY_TOP_KS),
            "probability_floors": list(PROBABILITY_FLOORS),
            "fee_bps": float(FEE_BPS),
            "sample_every_minutes": v96.SAMPLE_EVERY_MINUTES,
            "selector_days": v96.SELECTOR_DAYS,
            "holdout_days": v96.HOLDOUT_DAYS,
            "horizon_meta": metas,
        },
        "decision": {
            "passing_candidate_count": int(len(passed)),
            **decision,
        },
        "outputs": {
            "candidates": str(candidates_path),
            "passed_candidates": str(passed_path),
            "selected_candidate": str(selected_path),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v106_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload, candidates, selected_row, passed)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
