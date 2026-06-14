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
import run_btcusdc_v107_price_context_exact_daily_classifier as v107
import run_btcusdc_v108_technical_indicator_exact_daily_classifier as v108
import run_btcusdc_v109_feature_family_ensemble_exact_daily as v109


OUT_DIR = ROOT / "runs" / "research_v110_btcusdc_flow_sweep_regime_ensemble"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V110_BTCUSDC_FLOW_SWEEP_REGIME_ENSEMBLE_RESULTS.md"
V109_SELECTED_PATH = v109.OUT_DIR / "v109_selector_locked_selected_candidate.csv"

FLOW_WINDOWS = (5, 15, 30, 60, 120, 240)
INTENSITY_WINDOWS = (15, 60, 240)
SWEEP_WINDOWS = (30, 60, 240)
REGIME_WINDOWS = (60, 240)

FLOW_SWEEP_REGIME_FEATURE_COLUMNS = [
    *[f"signed_flow_mean_{window}" for window in FLOW_WINDOWS],
    *[f"signed_flow_sum_{window}" for window in FLOW_WINDOWS],
    *[f"signed_flow_std_{window}" for window in FLOW_WINDOWS],
    *[f"signed_volume_sum_{window}" for window in FLOW_WINDOWS],
    *[f"signed_volume_ratio_{window}" for window in FLOW_WINDOWS],
    *[f"buy_ratio_mean_{window}" for window in INTENSITY_WINDOWS],
    *[f"buy_ratio_z_{window}" for window in INTENSITY_WINDOWS],
    *[f"trade_count_z_{window}" for window in INTENSITY_WINDOWS],
    *[f"volume_intensity_z_{window}" for window in INTENSITY_WINDOWS],
    *[f"cvd_slope_{window}" for window in INTENSITY_WINDOWS],
    *[f"cvd_slope_norm_{window}" for window in INTENSITY_WINDOWS],
    *[f"cvd_price_divergence_{window}" for window in INTENSITY_WINDOWS],
    *[f"prior_high_sweep_{window}" for window in SWEEP_WINDOWS],
    *[f"prior_low_sweep_{window}" for window in SWEEP_WINDOWS],
    *[f"high_sweep_flow_confirm_{window}" for window in SWEEP_WINDOWS],
    *[f"low_sweep_flow_confirm_{window}" for window in SWEEP_WINDOWS],
    *[f"high_sweep_flow_fade_{window}" for window in SWEEP_WINDOWS],
    *[f"low_sweep_flow_fade_{window}" for window in SWEEP_WINDOWS],
    *[f"dist_prior_high_{window}_bps" for window in SWEEP_WINDOWS],
    *[f"dist_prior_low_{window}_bps" for window in SWEEP_WINDOWS],
    *[f"realized_vol_z_{window}" for window in REGIME_WINDOWS],
    *[f"range_z_{window}" for window in REGIME_WINDOWS],
    *[f"flow_vol_interaction_{window}" for window in REGIME_WINDOWS],
]

FEATURE_FAMILY_SETS = {
    "ma_flow": ("ma", "flow_sweep_regime"),
    "ma_price_flow": ("ma", "price_context", "flow_sweep_regime"),
    "ma_technical_flow": ("ma", "technical", "flow_sweep_regime"),
    "ma_price_technical_flow": ("ma", "price_context", "technical", "flow_sweep_regime"),
}

HORIZONS = v106.HORIZONS
PROBABILITY_FLOORS = v106.PROBABILITY_FLOORS
DAILY_TOP_KS = v106.DAILY_TOP_KS
FEE_BPS = v106.FEE_BPS


def _zscore(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(int(window), min_periods=int(window)).mean()
    std = series.rolling(int(window), min_periods=int(window)).std()
    return (series - mean) / std.replace(0.0, np.nan)


def _add_flow_sweep_regime_features(
    bars: pd.DataFrame,
    *,
    flow_windows: tuple[int, ...] = FLOW_WINDOWS,
    intensity_windows: tuple[int, ...] = INTENSITY_WINDOWS,
    sweep_windows: tuple[int, ...] = SWEEP_WINDOWS,
    regime_windows: tuple[int, ...] = REGIME_WINDOWS,
) -> pd.DataFrame:
    out = bars.copy().sort_values("timestamp").reset_index(drop=True)
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    open_px = pd.to_numeric(out["open"], errors="coerce")
    prior_close = pd.to_numeric(out["close"], errors="coerce").shift(1)
    prior_high = pd.to_numeric(out["high"], errors="coerce").shift(1)
    prior_low = pd.to_numeric(out["low"], errors="coerce").shift(1)
    prior_high_for_sweep = pd.to_numeric(out["high"], errors="coerce").shift(2)
    prior_low_for_sweep = pd.to_numeric(out["low"], errors="coerce").shift(2)
    prior_volume = pd.to_numeric(out["volume"], errors="coerce").shift(1)
    prior_trade_count = pd.to_numeric(out.get("trade_count", pd.Series(0.0, index=out.index)), errors="coerce").shift(1)
    prior_buy_ratio = pd.to_numeric(out.get("taker_buy_ratio", pd.Series(0.5, index=out.index)), errors="coerce").shift(1)
    prior_flow = pd.to_numeric(out.get("signed_taker_imbalance", pd.Series(0.0, index=out.index)), errors="coerce").shift(1)
    prior_signed_volume = (
        pd.to_numeric(out.get("taker_buy_volume", pd.Series(0.0, index=out.index)), errors="coerce")
        - pd.to_numeric(out.get("taker_sell_volume", pd.Series(0.0, index=out.index)), errors="coerce")
    ).shift(1)
    prior_abs_volume = prior_volume.abs().replace(0.0, np.nan)
    prior_return = prior_close.pct_change() * 10000.0
    prior_range_bps = (prior_high / prior_low.replace(0.0, np.nan) - 1.0) * 10000.0
    cvd = prior_signed_volume.fillna(0.0).cumsum()

    for window in flow_windows:
        window = int(window)
        flow_mean = prior_flow.rolling(window, min_periods=window).mean()
        flow_sum = prior_flow.rolling(window, min_periods=window).sum()
        flow_std = prior_flow.rolling(window, min_periods=window).std()
        signed_volume_sum = prior_signed_volume.rolling(window, min_periods=window).sum()
        volume_sum = prior_abs_volume.rolling(window, min_periods=window).sum()
        out[f"signed_flow_mean_{window}"] = flow_mean
        out[f"signed_flow_sum_{window}"] = flow_sum
        out[f"signed_flow_std_{window}"] = flow_std
        out[f"signed_volume_sum_{window}"] = signed_volume_sum
        out[f"signed_volume_ratio_{window}"] = signed_volume_sum / volume_sum.replace(0.0, np.nan)

    for window in intensity_windows:
        window = int(window)
        out[f"buy_ratio_mean_{window}"] = prior_buy_ratio.rolling(window, min_periods=window).mean()
        out[f"buy_ratio_z_{window}"] = _zscore(prior_buy_ratio, window)
        out[f"trade_count_z_{window}"] = _zscore(prior_trade_count, window)
        out[f"volume_intensity_z_{window}"] = _zscore(prior_volume, window)
        cvd_slope = cvd - cvd.shift(window)
        volume_sum = prior_abs_volume.rolling(window, min_periods=window).sum()
        price_return = (prior_close / prior_close.shift(window) - 1.0) * 10000.0
        out[f"cvd_slope_{window}"] = cvd_slope
        out[f"cvd_slope_norm_{window}"] = cvd_slope / volume_sum.replace(0.0, np.nan)
        out[f"cvd_price_divergence_{window}"] = np.sign(cvd_slope) * np.sign(price_return) * np.minimum(
            np.abs(cvd_slope / volume_sum.replace(0.0, np.nan)),
            5.0,
        )

    for window in sweep_windows:
        window = int(window)
        rolling_high = prior_high_for_sweep.rolling(window, min_periods=window).max()
        rolling_low = prior_low_for_sweep.rolling(window, min_periods=window).min()
        high_sweep = (prior_high >= rolling_high).astype(float)
        low_sweep = (prior_low <= rolling_low).astype(float)
        flow_sum = prior_flow.rolling(window, min_periods=window).sum()
        out[f"prior_high_sweep_{window}"] = high_sweep
        out[f"prior_low_sweep_{window}"] = low_sweep
        out[f"high_sweep_flow_confirm_{window}"] = high_sweep * (flow_sum > 0.0).astype(float)
        out[f"low_sweep_flow_confirm_{window}"] = low_sweep * (flow_sum < 0.0).astype(float)
        out[f"high_sweep_flow_fade_{window}"] = high_sweep * (flow_sum <= 0.0).astype(float)
        out[f"low_sweep_flow_fade_{window}"] = low_sweep * (flow_sum >= 0.0).astype(float)
        out[f"dist_prior_high_{window}_bps"] = (open_px / rolling_high - 1.0) * 10000.0
        out[f"dist_prior_low_{window}_bps"] = (open_px / rolling_low - 1.0) * 10000.0

    for window in regime_windows:
        window = int(window)
        realized_vol = prior_return.rolling(window, min_periods=window).std()
        range_mean = prior_range_bps.rolling(window, min_periods=window).mean()
        flow_abs_mean = prior_flow.abs().rolling(window, min_periods=window).mean()
        out[f"realized_vol_z_{window}"] = _zscore(realized_vol, window)
        out[f"range_z_{window}"] = _zscore(prior_range_bps, window)
        out[f"flow_vol_interaction_{window}"] = flow_abs_mean * realized_vol / range_mean.replace(0.0, np.nan)

    return out


def _flow_sweep_regime_feature_frame(bars: pd.DataFrame, *, horizon_minutes: int) -> tuple[pd.DataFrame, list[str]]:
    sampled, feature_cols = v102._ma_feature_frame(bars, horizon_minutes=int(horizon_minutes))
    flow_frame = _add_flow_sweep_regime_features(bars)[["timestamp", *FLOW_SWEEP_REGIME_FEATURE_COLUMNS]].copy()
    sampled = sampled.merge(flow_frame, on="timestamp", how="left")
    for column in FLOW_SWEEP_REGIME_FEATURE_COLUMNS:
        if column not in feature_cols:
            feature_cols.append(column)
    sampled[feature_cols] = sampled[feature_cols].replace([np.inf, -np.inf], np.nan)
    return sampled, feature_cols


def _feature_frame_for_family(family: str, bars: pd.DataFrame, *, horizon_minutes: int) -> tuple[pd.DataFrame, list[str]]:
    if family == "ma":
        return v102._ma_feature_frame(bars, horizon_minutes=int(horizon_minutes))
    if family == "price_context":
        return v107._price_context_feature_frame(bars, horizon_minutes=int(horizon_minutes))
    if family == "technical":
        return v108._technical_indicator_feature_frame(bars, horizon_minutes=int(horizon_minutes))
    if family == "flow_sweep_regime":
        return _flow_sweep_regime_feature_frame(bars, horizon_minutes=int(horizon_minutes))
    raise ValueError(f"unknown feature family: {family}")


def _average_probability_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    return v109._average_probability_frames(frames)


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
    required_families = sorted({family for families in FEATURE_FAMILY_SETS.values() for family in families})
    selector_by_family: dict[str, pd.DataFrame] = {}
    holdout_by_family: dict[str, pd.DataFrame] = {}
    family_metas: list[dict[str, object]] = []
    for family in required_families:
        selector_pred, holdout_pred, family_meta = _family_predictions(bars, horizon=int(horizon), family=family)
        selector_by_family[family] = selector_pred
        holdout_by_family[family] = holdout_pred
        family_metas.append(family_meta)

    rows: list[dict[str, object]] = []
    ledgers: dict[str, pd.DataFrame] = {}
    combo_metas: list[dict[str, object]] = []

    for family_set_name, families in FEATURE_FAMILY_SETS.items():
        selector_pred = _average_probability_frames([selector_by_family[family] for family in families])
        holdout_pred = _average_probability_frames([holdout_by_family[family] for family in families])
        if selector_pred.empty or holdout_pred.empty:
            combo_metas.append({"family_set": family_set_name, "skipped": True, "reason": "empty ensemble predictions"})
            continue

        selector_start_ts = pd.to_datetime(selector_pred["timestamp"].min(), utc=True)
        selector_end_ts = pd.to_datetime(selector_pred["timestamp"].max(), utc=True)
        holdout_start_ts = pd.to_datetime(holdout_pred["timestamp"].min(), utc=True)
        holdout_end_ts = pd.to_datetime(holdout_pred["timestamp"].max(), utc=True)
        combo_metas.append(
            {
                "family_set": family_set_name,
                "families": list(families),
                "selector_start_timestamp": selector_start_ts.isoformat(),
                "holdout_start_timestamp": holdout_start_ts.isoformat(),
                "holdout_end_timestamp": holdout_end_ts.isoformat(),
            }
        )

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
                    "policy_id": (
                        f"hgb_v110_{family_set_name}_exact_daily_top{int(daily_top_k)}"
                        f"_h{int(horizon)}_p{float(probability_floor):.6f}"
                    ),
                    "family_set": family_set_name,
                    "feature_families": "+".join(families),
                    "horizon_minutes": int(horizon),
                    "daily_top_k": int(daily_top_k),
                    "probability_floor": float(probability_floor),
                    "fee_bps": float(FEE_BPS),
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
        "family_meta": family_metas,
        "combo_meta": combo_metas,
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
        print(f"evaluated V110 flow/sweep/regime ensemble horizon {horizon} with {len(horizon_rows)} policies", flush=True)
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
        "v110_policy_id": str(current["policy_id"]),
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
        return {"promote_over_v109": True, "reason": "holdout PnL improved by at least 500 bps under exact-daily gate"}
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
        "family_set",
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
        "holdout_worst_month_net_pnl_bps",
    ]
    top = candidates.head(16).copy() if not candidates.empty else pd.DataFrame()
    comparison_lines = ["Comparison unavailable."]
    if comparison.get("available"):
        comparison_lines = [
            f"- V109 policy: `{comparison['v109_policy_id']}`",
            f"- V110 policy: `{comparison['v110_policy_id']}`",
            f"- Selector PnL delta: `{comparison['selector_total_net_pnl_bps_delta']:.6f}` bps",
            f"- Selector win-rate delta: `{comparison['selector_win_rate_delta']:.6f}`",
            f"- Selector max-drawdown delta: `{comparison['selector_max_drawdown_bps_delta']:.6f}` bps",
            f"- Holdout PnL delta: `{comparison['holdout_total_net_pnl_bps_delta']:.6f}` bps",
            f"- Holdout win-rate delta: `{comparison['holdout_win_rate_delta']:.6f}`",
            f"- Holdout max-drawdown delta: `{comparison['holdout_max_drawdown_bps_delta']:.6f}` bps",
        ]
    lines = [
        "# Research V110 BTCUSDC Flow Sweep Regime Ensemble Results",
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
        f"- Flow/sweep/regime features added: `{len(FLOW_SWEEP_REGIME_FEATURE_COLUMNS)}`",
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
        "V110 adds prior-only order-flow, CVD divergence, sweep, trade-intensity, and volatility-regime features, then evaluates selector-locked exact-daily ensembles against V109. This remains a research candidate, not a live trading guarantee.",
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
    comparison = _comparison_against_v109(selected_row)
    promotion = _promotion_decision(selected_row, comparison)

    candidates_path = OUT_DIR / "v110_flow_sweep_regime_ensemble_candidates.csv"
    passed_path = OUT_DIR / "v110_flow_sweep_regime_ensemble_passed_candidates.csv"
    selected_path = OUT_DIR / "v110_selector_locked_selected_candidate.csv"
    candidates.to_csv(candidates_path, index=False)
    passed.to_csv(passed_path, index=False)
    selected_row.to_csv(selected_path, index=False)
    for policy_id, ledger in ledgers.items():
        ledger.to_csv(OUT_DIR / f"v110_{policy_id}_trade_ledger.csv", index=False)

    payload = {
        "version": "v110_btcusdc_flow_sweep_regime_ensemble",
        "scan": {
            "candidate_count": int(len(candidates)),
            "horizons": list(HORIZONS),
            "daily_top_ks": list(DAILY_TOP_KS),
            "probability_floors": list(PROBABILITY_FLOORS),
            "fee_bps": float(FEE_BPS),
            "feature_family_sets": {key: list(value) for key, value in FEATURE_FAMILY_SETS.items()},
            "flow_sweep_regime_feature_count": int(len(FLOW_SWEEP_REGIME_FEATURE_COLUMNS)),
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
    (OUT_DIR / "v110_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload, candidates, selected_row, passed, comparison)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
