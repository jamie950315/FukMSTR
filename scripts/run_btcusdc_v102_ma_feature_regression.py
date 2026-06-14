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
import run_btcusdc_v101_thick_edge_regression as v101


OUT_DIR = ROOT / "runs" / "research_v102_btcusdc_ma_feature_regression"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V102_BTCUSDC_MA_FEATURE_REGRESSION_RESULTS.md"

MA_WINDOWS = (7, 25, 99)
MA_FEATURE_COLUMNS = [
    "ma7_dist_bps",
    "ma25_dist_bps",
    "ma99_dist_bps",
    "ma7_ma25_spread_bps",
    "ma25_ma99_spread_bps",
    "ma7_slope_5_bps",
    "ma25_slope_5_bps",
    "ma99_slope_5_bps",
    "ma_stack_long",
    "ma_stack_short",
]


def _add_ma_features(bars: pd.DataFrame) -> pd.DataFrame:
    out = bars.copy().sort_values("timestamp").reset_index(drop=True)
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    open_px = pd.to_numeric(out["open"], errors="coerce")
    prior_close = pd.to_numeric(out["close"], errors="coerce").shift(1)
    for window in MA_WINDOWS:
        out[f"ma{window}"] = prior_close.rolling(int(window), min_periods=int(window)).mean()
        out[f"ma{window}_dist_bps"] = (open_px / out[f"ma{window}"] - 1.0) * 10000.0
        out[f"ma{window}_slope_5_bps"] = (out[f"ma{window}"] / out[f"ma{window}"].shift(5) - 1.0) * 10000.0
    out["ma7_ma25_spread_bps"] = (out["ma7"] / out["ma25"] - 1.0) * 10000.0
    out["ma25_ma99_spread_bps"] = (out["ma25"] / out["ma99"] - 1.0) * 10000.0
    out["ma_stack_long"] = ((out["ma7"] > out["ma25"]) & (out["ma25"] > out["ma99"])).astype(float)
    out["ma_stack_short"] = ((out["ma7"] < out["ma25"]) & (out["ma25"] < out["ma99"])).astype(float)
    return out


def _ma_feature_frame(bars: pd.DataFrame, *, horizon_minutes: int) -> tuple[pd.DataFrame, list[str]]:
    sampled, feature_cols = v96._feature_frame(bars, horizon_minutes=int(horizon_minutes))
    ma_frame = _add_ma_features(bars)[["timestamp", *MA_FEATURE_COLUMNS]].copy()
    sampled = sampled.merge(ma_frame, on="timestamp", how="left")
    for column in MA_FEATURE_COLUMNS:
        if column not in feature_cols:
            feature_cols.append(column)
    sampled[feature_cols] = sampled[feature_cols].replace([np.inf, -np.inf], np.nan)
    return sampled, feature_cols


def _evaluate_horizon(bars: pd.DataFrame, *, horizon: int) -> tuple[list[dict[str, object]], dict[str, pd.DataFrame], dict[str, object]]:
    data, feature_cols = _ma_feature_frame(bars, horizon_minutes=int(horizon))
    full_end = pd.to_datetime(data["timestamp"].max(), utc=True)
    holdout_start = full_end - pd.Timedelta(days=v96.HOLDOUT_DAYS)
    selector_start = holdout_start - pd.Timedelta(days=v96.SELECTOR_DAYS)
    train = data.loc[data["timestamp"] < selector_start].copy()
    selector = data.loc[(data["timestamp"] >= selector_start) & (data["timestamp"] < holdout_start)].copy()
    holdout = data.loc[data["timestamp"] >= holdout_start].copy()
    if len(train) < 1000 or len(selector) < 100 or len(holdout) < 100:
        return [], {}, {"horizon_minutes": int(horizon), "skipped": True, "reason": "insufficient rows"}

    model = v101._fit_regressor(train, feature_cols)
    selector_pred = v101._prediction_frame(model, selector, feature_cols)
    holdout_pred = v101._prediction_frame(model, holdout, feature_cols)
    selector_start_ts = pd.to_datetime(selector["timestamp"].min(), utc=True)
    selector_end_ts = pd.to_datetime(selector["timestamp"].max(), utc=True)
    holdout_start_ts = pd.to_datetime(holdout["timestamp"].min(), utc=True)
    holdout_end_ts = pd.to_datetime(holdout["timestamp"].max(), utc=True)
    rows: list[dict[str, object]] = []
    ledgers: dict[str, pd.DataFrame] = {}

    for edge_threshold in v101.EDGE_THRESHOLDS_BPS:
        selector_ledger = v101._edge_prediction_ledger(
            selector_pred,
            edge_threshold_bps=float(edge_threshold),
            horizon_minutes=int(horizon),
            fee_bps=v101.FEE_BPS,
        )
        holdout_ledger = v101._edge_prediction_ledger(
            holdout_pred,
            edge_threshold_bps=float(edge_threshold),
            horizon_minutes=int(horizon),
            fee_bps=v101.FEE_BPS,
        )
        selector_summary = v94._trade_summary(selector_ledger, start_ts=selector_start_ts, end_ts=selector_end_ts)
        holdout_summary = v94._trade_summary(holdout_ledger, start_ts=holdout_start_ts, end_ts=holdout_end_ts)
        row = {
            "policy_id": f"hgb_ma_reg_h{int(horizon)}_edge{float(edge_threshold):g}",
            "horizon_minutes": int(horizon),
            "edge_threshold_bps": float(edge_threshold),
            "fee_bps": float(v101.FEE_BPS),
            "train_rows": int(len(train)),
            "selector_rows": int(len(selector)),
            "holdout_rows": int(len(holdout)),
            "feature_count": int(len(feature_cols)),
            **{f"selector_{key}": value for key, value in selector_summary.items()},
            **{f"holdout_{key}": value for key, value in holdout_summary.items()},
        }
        row["passed_ma_feature_gate"] = bool(v101._passes_thick_edge_gate(row))
        rows.append(row)
        if bool(row["passed_ma_feature_gate"]):
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
        "ma_feature_columns": list(MA_FEATURE_COLUMNS),
        "selector_start_timestamp": selector_start_ts.isoformat(),
        "holdout_start_timestamp": holdout_start_ts.isoformat(),
        "holdout_end_timestamp": holdout_end_ts.isoformat(),
    }
    return rows, ledgers, meta


def _scan(bars: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    ledgers: dict[str, pd.DataFrame] = {}
    metas: list[dict[str, object]] = []
    for horizon in v101.HORIZONS:
        horizon_rows, horizon_ledgers, meta = _evaluate_horizon(bars, horizon=int(horizon))
        rows.extend(horizon_rows)
        ledgers.update(horizon_ledgers)
        metas.append(meta)
        print(f"evaluated MA feature regression horizon {horizon} with {len(horizon_rows)} thresholds", flush=True)
    candidates = pd.DataFrame(rows)
    if not candidates.empty:
        candidates = candidates.sort_values(
            [
                "passed_ma_feature_gate",
                "holdout_total_net_pnl_bps",
                "holdout_win_rate",
                "selector_total_net_pnl_bps",
                "holdout_avg_trades_per_calendar_day",
            ],
            ascending=[False, False, False, False, False],
        ).reset_index(drop=True)
    return candidates, ledgers, metas


def _write_report(payload: dict[str, object], candidates: pd.DataFrame, passed: pd.DataFrame) -> None:
    report_cols = [
        "policy_id",
        "passed_ma_feature_gate",
        "horizon_minutes",
        "edge_threshold_bps",
        "feature_count",
        "selector_trade_count",
        "selector_avg_trades_per_calendar_day",
        "selector_total_net_pnl_bps",
        "selector_win_rate",
        "selector_calendar_positive_month_rate",
        "holdout_trade_count",
        "holdout_avg_trades_per_calendar_day",
        "holdout_total_net_pnl_bps",
        "holdout_win_rate",
        "holdout_calendar_positive_month_rate",
    ]
    top = candidates.head(12).copy() if not candidates.empty else pd.DataFrame()
    lines = [
        "# Research V102 BTCUSDC MA Feature Regression Results",
        "",
        "## Decision",
        "",
        f"- Evaluated candidates: `{payload['scan']['candidate_count']}`",
        f"- Passing MA-feature candidates: `{payload['decision']['passing_candidate_count']}`",
        f"- Selected candidate: `{payload['decision']['selected_policy']}`",
        f"- Fee: `{v101.FEE_BPS}` bps",
        f"- MA windows: `{list(MA_WINDOWS)}`",
        "",
        "## Top Candidates",
        "",
        top[report_cols].to_csv(index=False).strip() if not top.empty else "No candidates were produced.",
        "",
        "## Passing Candidates",
        "",
        passed[report_cols].to_csv(index=False).strip() if not passed.empty else "No candidate passed the MA-feature gate.",
        "",
        "## Interpretation",
        "",
        "V102 adds MA7, MA25, and MA99 trend-structure features to the V101 thick-edge regression route. MA features are computed from prior close values to avoid lookahead. This is a research scan, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    bars = v94._full_bars()
    candidates, ledgers, metas = _scan(bars)
    passed = candidates.loc[candidates["passed_ma_feature_gate"]].copy() if not candidates.empty else pd.DataFrame()

    candidates_path = OUT_DIR / "v102_ma_feature_candidates.csv"
    passed_path = OUT_DIR / "v102_ma_feature_passed_candidates.csv"
    candidates.to_csv(candidates_path, index=False)
    passed.to_csv(passed_path, index=False)
    for policy_id, ledger in ledgers.items():
        ledger.to_csv(OUT_DIR / f"v102_{policy_id}_trade_ledger.csv", index=False)

    selected = str(passed.iloc[0]["policy_id"]) if not passed.empty else None
    payload = {
        "version": "v102_btcusdc_ma_feature_regression",
        "scan": {
            "candidate_count": int(len(candidates)),
            "horizons": list(v101.HORIZONS),
            "edge_thresholds_bps": list(v101.EDGE_THRESHOLDS_BPS),
            "fee_bps": float(v101.FEE_BPS),
            "ma_windows": list(MA_WINDOWS),
            "ma_feature_columns": list(MA_FEATURE_COLUMNS),
            "sample_every_minutes": v96.SAMPLE_EVERY_MINUTES,
            "selector_days": v96.SELECTOR_DAYS,
            "holdout_days": v96.HOLDOUT_DAYS,
            "horizon_meta": metas,
        },
        "decision": {
            "passing_candidate_count": int(len(passed)),
            "selected_policy": selected,
            "goal_satisfied_by_scan": bool(selected is not None),
            "failed_reason": None if selected is not None else "no candidate passed the 8.5 bps MA-feature high-frequency gate",
        },
        "outputs": {
            "candidates": str(candidates_path),
            "passed_candidates": str(passed_path),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v102_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload, candidates, passed)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
