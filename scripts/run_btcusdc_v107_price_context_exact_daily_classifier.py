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
import run_btcusdc_v102_ma_feature_regression as v102
import run_btcusdc_v104_ma_hgb_daily_topk_classifier as v104
import run_btcusdc_v106_exact_daily_coverage_classifier as v106


OUT_DIR = ROOT / "runs" / "research_v107_btcusdc_price_context_exact_daily_classifier"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V107_BTCUSDC_PRICE_CONTEXT_EXACT_DAILY_CLASSIFIER_RESULTS.md"
V106_SELECTED_PATH = v106.OUT_DIR / "v106_selector_locked_selected_candidate.csv"

PRICE_CONTEXT_WINDOWS = (15, 30, 60, 120, 240)
VOLUME_CONTEXT_WINDOWS = (30, 60, 120, 240)

PRICE_CONTEXT_FEATURE_COLUMNS = [
    *[f"prior_high_{window}_dist_bps" for window in PRICE_CONTEXT_WINDOWS],
    *[f"prior_low_{window}_dist_bps" for window in PRICE_CONTEXT_WINDOWS],
    *[f"range_pos_{window}" for window in PRICE_CONTEXT_WINDOWS],
    *[f"range_width_{window}_bps" for window in PRICE_CONTEXT_WINDOWS],
    *[f"realized_vol_{window}_bps" for window in PRICE_CONTEXT_WINDOWS],
    *[f"volume_z_{window}" for window in VOLUME_CONTEXT_WINDOWS],
]

HORIZONS = v106.HORIZONS
PROBABILITY_FLOORS = v106.PROBABILITY_FLOORS
DAILY_TOP_KS = v106.DAILY_TOP_KS
FEE_BPS = v106.FEE_BPS


def _add_price_context_features(
    bars: pd.DataFrame,
    *,
    windows: tuple[int, ...] = PRICE_CONTEXT_WINDOWS,
    volume_windows: tuple[int, ...] = VOLUME_CONTEXT_WINDOWS,
) -> pd.DataFrame:
    out = bars.copy().sort_values("timestamp").reset_index(drop=True)
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    open_px = pd.to_numeric(out["open"], errors="coerce")
    prior_high = pd.to_numeric(out["high"], errors="coerce").shift(1)
    prior_low = pd.to_numeric(out["low"], errors="coerce").shift(1)
    prior_close = pd.to_numeric(out["close"], errors="coerce").shift(1)
    prior_volume = pd.to_numeric(out["volume"], errors="coerce").shift(1)
    prior_return = prior_close.pct_change() * 10000.0

    for window in windows:
        window = int(window)
        rolling_high = prior_high.rolling(window, min_periods=window).max()
        rolling_low = prior_low.rolling(window, min_periods=window).min()
        range_width = rolling_high - rolling_low
        out[f"prior_high_{window}"] = rolling_high
        out[f"prior_low_{window}"] = rolling_low
        out[f"prior_high_{window}_dist_bps"] = (open_px / rolling_high - 1.0) * 10000.0
        out[f"prior_low_{window}_dist_bps"] = (open_px / rolling_low - 1.0) * 10000.0
        out[f"range_pos_{window}"] = (open_px - rolling_low) / range_width.replace(0.0, np.nan)
        out[f"range_width_{window}_bps"] = (rolling_high / rolling_low - 1.0) * 10000.0
        out[f"realized_vol_{window}_bps"] = prior_return.rolling(window, min_periods=window).std()

    for window in volume_windows:
        window = int(window)
        volume_mean = prior_volume.rolling(window, min_periods=window).mean()
        volume_std = prior_volume.rolling(window, min_periods=window).std()
        out[f"volume_z_{window}"] = (prior_volume - volume_mean) / volume_std.replace(0.0, np.nan)

    return out


def _price_context_feature_frame(bars: pd.DataFrame, *, horizon_minutes: int) -> tuple[pd.DataFrame, list[str]]:
    sampled, feature_cols = v102._ma_feature_frame(bars, horizon_minutes=int(horizon_minutes))
    context_frame = _add_price_context_features(bars)[["timestamp", *PRICE_CONTEXT_FEATURE_COLUMNS]].copy()
    sampled = sampled.merge(context_frame, on="timestamp", how="left")
    for column in PRICE_CONTEXT_FEATURE_COLUMNS:
        if column not in feature_cols:
            feature_cols.append(column)
    sampled[feature_cols] = sampled[feature_cols].replace([np.inf, -np.inf], np.nan)
    return sampled, feature_cols


def _evaluate_horizon(bars: pd.DataFrame, *, horizon: int) -> tuple[list[dict[str, object]], dict[str, pd.DataFrame], dict[str, object]]:
    data, feature_cols = _price_context_feature_frame(bars, horizon_minutes=int(horizon))
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
                "policy_id": f"hgb_price_context_exact_daily_top{int(daily_top_k)}_h{int(horizon)}_p{float(probability_floor):.6f}",
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
            row["passed_exact_daily_gate"] = bool(v106._passes_exact_daily_gate(row))
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
        "price_context_feature_count": int(len(PRICE_CONTEXT_FEATURE_COLUMNS)),
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
        print(f"evaluated price-context exact-daily classifier horizon {horizon} with {len(horizon_rows)} policies", flush=True)
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
        "v107_policy_id": str(current["policy_id"]),
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
        "feature_count",
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
            f"- V107 policy: `{comparison['v107_policy_id']}`",
            f"- Selector PnL delta: `{comparison['selector_total_net_pnl_bps_delta']:.6f}` bps",
            f"- Selector win-rate delta: `{comparison['selector_win_rate_delta']:.6f}`",
            f"- Holdout PnL delta: `{comparison['holdout_total_net_pnl_bps_delta']:.6f}` bps",
            f"- Holdout win-rate delta: `{comparison['holdout_win_rate_delta']:.6f}`",
            f"- Holdout max-drawdown delta: `{comparison['holdout_max_drawdown_bps_delta']:.6f}` bps",
        ]
    lines = [
        "# Research V107 BTCUSDC Price Context Exact Daily Classifier Results",
        "",
        "## Decision",
        "",
        f"- Evaluated candidates: `{payload['scan']['candidate_count']}`",
        f"- Passing exact-daily candidates: `{payload['decision']['passing_candidate_count']}`",
        f"- Selector-locked selected candidate: `{payload['decision']['selected_policy']}`",
        f"- Holdout passed after selector lock: `{payload['decision']['selector_locked_holdout_passed']}`",
        f"- Goal satisfied by strict exact-daily selection: `{payload['decision']['goal_satisfied_by_selector_locked_exact_daily_selection']}`",
        f"- Price-context features added: `{len(PRICE_CONTEXT_FEATURE_COLUMNS)}`",
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
        "V107 adds prior high/low, rolling range-position, realized-volatility, and prior-volume z-score features to the V106 exact-daily classifier. All new rolling features use prior bars only. This remains a research candidate, not a live trading guarantee.",
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

    candidates_path = OUT_DIR / "v107_price_context_candidates.csv"
    passed_path = OUT_DIR / "v107_price_context_passed_candidates.csv"
    selected_path = OUT_DIR / "v107_selector_locked_selected_candidate.csv"
    candidates.to_csv(candidates_path, index=False)
    passed.to_csv(passed_path, index=False)
    selected_row.to_csv(selected_path, index=False)
    for policy_id, ledger in ledgers.items():
        ledger.to_csv(OUT_DIR / f"v107_{policy_id}_trade_ledger.csv", index=False)

    payload = {
        "version": "v107_btcusdc_price_context_exact_daily_classifier",
        "scan": {
            "candidate_count": int(len(candidates)),
            "horizons": list(HORIZONS),
            "daily_top_ks": list(DAILY_TOP_KS),
            "probability_floors": list(PROBABILITY_FLOORS),
            "fee_bps": float(FEE_BPS),
            "ma_feature_columns": list(v102.MA_FEATURE_COLUMNS),
            "price_context_feature_columns": list(PRICE_CONTEXT_FEATURE_COLUMNS),
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
    (OUT_DIR / "v107_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload, candidates, selected_row, passed, comparison)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
