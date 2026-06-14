from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_btcusdc_v94_high_frequency_scan as v94
import run_btcusdc_v96_ml_probability_gate as v96


OUT_DIR = ROOT / "runs" / "research_v101_btcusdc_thick_edge_regression"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V101_BTCUSDC_THICK_EDGE_REGRESSION_RESULTS.md"

HORIZONS = (15, 30, 60, 120)
EDGE_THRESHOLDS_BPS = (8.5, 10.0, 12.5, 15.0, 20.0, 25.0, 30.0, 40.0)
FEE_BPS = 8.5

MIN_WIN_RATE = 0.55
MIN_AVG_TRADES_PER_CALENDAR_DAY = 1.0
MIN_CALENDAR_POSITIVE_MONTH_RATE = 0.50


def _edge_prediction_ledger(
    predictions: pd.DataFrame,
    *,
    edge_threshold_bps: float,
    horizon_minutes: int,
    fee_bps: float,
) -> pd.DataFrame:
    frame = predictions.copy()
    pred = pd.to_numeric(frame["predicted_return_bps"], errors="coerce").fillna(0.0)
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[pred >= float(edge_threshold_bps)] = 1
    signal.loc[pred <= -float(edge_threshold_bps)] = -1
    eligible = signal != 0
    keep_idx = v94._spaced_indices(eligible, horizon=int(horizon_minutes))
    if keep_idx.size == 0:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "signal",
                "future_return_bps",
                "predicted_return_bps",
                "gross_pnl_bps",
                "net_pnl_bps",
                "edge_threshold_bps",
                "horizon_minutes",
            ]
        )
    kept = frame.iloc[keep_idx].copy()
    kept_signal = signal.iloc[keep_idx].astype(int).to_numpy()
    future = pd.to_numeric(kept["future_return_bps"], errors="coerce").fillna(0.0).to_numpy(float)
    predicted = pd.to_numeric(kept["predicted_return_bps"], errors="coerce").fillna(0.0).to_numpy(float)
    gross = future * kept_signal
    ledger = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(kept["timestamp"], utc=True).to_numpy(),
            "signal": kept_signal,
            "future_return_bps": future,
            "predicted_return_bps": predicted,
            "gross_pnl_bps": gross,
            "net_pnl_bps": gross - float(fee_bps),
            "edge_threshold_bps": float(edge_threshold_bps),
            "horizon_minutes": int(horizon_minutes),
        }
    )
    ledger["equity_bps"] = pd.to_numeric(ledger["net_pnl_bps"], errors="coerce").fillna(0.0).cumsum()
    return ledger


def _passes_thick_edge_gate(row: dict[str, object]) -> bool:
    return (
        float(row["selector_total_net_pnl_bps"]) > 0.0
        and float(row["holdout_total_net_pnl_bps"]) > 0.0
        and float(row["selector_win_rate"]) > MIN_WIN_RATE
        and float(row["holdout_win_rate"]) > MIN_WIN_RATE
        and float(row["selector_avg_trades_per_calendar_day"]) >= MIN_AVG_TRADES_PER_CALENDAR_DAY
        and float(row["holdout_avg_trades_per_calendar_day"]) >= MIN_AVG_TRADES_PER_CALENDAR_DAY
        and float(row["selector_calendar_positive_month_rate"]) >= MIN_CALENDAR_POSITIVE_MONTH_RATE
        and float(row["holdout_calendar_positive_month_rate"]) >= MIN_CALENDAR_POSITIVE_MONTH_RATE
    )


def _fit_regressor(train: pd.DataFrame, feature_cols: list[str]):
    model = make_pipeline(
        SimpleImputer(strategy="median"),
        HistGradientBoostingRegressor(
            max_iter=120,
            learning_rate=0.04,
            max_leaf_nodes=15,
            l2_regularization=0.10,
            early_stopping=True,
            validation_fraction=0.15,
            random_state=26101,
        ),
    )
    model.fit(train[feature_cols], pd.to_numeric(train["future_return_bps"], errors="coerce").fillna(0.0))
    return model


def _prediction_frame(model, frame: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    out = frame[["timestamp", "future_return_bps"]].copy()
    out["predicted_return_bps"] = model.predict(frame[feature_cols])
    return out


def _evaluate_horizon(bars: pd.DataFrame, *, horizon: int) -> tuple[list[dict[str, object]], dict[str, pd.DataFrame], dict[str, object]]:
    data, feature_cols = v96._feature_frame(bars, horizon_minutes=int(horizon))
    full_end = pd.to_datetime(data["timestamp"].max(), utc=True)
    holdout_start = full_end - pd.Timedelta(days=v96.HOLDOUT_DAYS)
    selector_start = holdout_start - pd.Timedelta(days=v96.SELECTOR_DAYS)
    train = data.loc[data["timestamp"] < selector_start].copy()
    selector = data.loc[(data["timestamp"] >= selector_start) & (data["timestamp"] < holdout_start)].copy()
    holdout = data.loc[data["timestamp"] >= holdout_start].copy()
    if len(train) < 1000 or len(selector) < 100 or len(holdout) < 100:
        return [], {}, {"horizon_minutes": int(horizon), "skipped": True, "reason": "insufficient rows"}

    model = _fit_regressor(train, feature_cols)
    selector_pred = _prediction_frame(model, selector, feature_cols)
    holdout_pred = _prediction_frame(model, holdout, feature_cols)
    selector_start_ts = pd.to_datetime(selector["timestamp"].min(), utc=True)
    selector_end_ts = pd.to_datetime(selector["timestamp"].max(), utc=True)
    holdout_start_ts = pd.to_datetime(holdout["timestamp"].min(), utc=True)
    holdout_end_ts = pd.to_datetime(holdout["timestamp"].max(), utc=True)
    rows: list[dict[str, object]] = []
    ledgers: dict[str, pd.DataFrame] = {}

    for edge_threshold in EDGE_THRESHOLDS_BPS:
        selector_ledger = _edge_prediction_ledger(
            selector_pred,
            edge_threshold_bps=float(edge_threshold),
            horizon_minutes=int(horizon),
            fee_bps=FEE_BPS,
        )
        holdout_ledger = _edge_prediction_ledger(
            holdout_pred,
            edge_threshold_bps=float(edge_threshold),
            horizon_minutes=int(horizon),
            fee_bps=FEE_BPS,
        )
        selector_summary = v94._trade_summary(selector_ledger, start_ts=selector_start_ts, end_ts=selector_end_ts)
        holdout_summary = v94._trade_summary(holdout_ledger, start_ts=holdout_start_ts, end_ts=holdout_end_ts)
        row = {
            "policy_id": f"hgb_reg_h{int(horizon)}_edge{float(edge_threshold):g}",
            "horizon_minutes": int(horizon),
            "edge_threshold_bps": float(edge_threshold),
            "fee_bps": float(FEE_BPS),
            "train_rows": int(len(train)),
            "selector_rows": int(len(selector)),
            "holdout_rows": int(len(holdout)),
            **{f"selector_{key}": value for key, value in selector_summary.items()},
            **{f"holdout_{key}": value for key, value in holdout_summary.items()},
        }
        row["passed_thick_edge_gate"] = bool(_passes_thick_edge_gate(row))
        rows.append(row)
        if bool(row["passed_thick_edge_gate"]):
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
        print(f"evaluated thick-edge regression horizon {horizon} with {len(horizon_rows)} thresholds", flush=True)
    candidates = pd.DataFrame(rows)
    if not candidates.empty:
        candidates = candidates.sort_values(
            [
                "passed_thick_edge_gate",
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
        "passed_thick_edge_gate",
        "horizon_minutes",
        "edge_threshold_bps",
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
        "# Research V101 BTCUSDC Thick Edge Regression Results",
        "",
        "## Decision",
        "",
        f"- Evaluated candidates: `{payload['scan']['candidate_count']}`",
        f"- Passing thick-edge candidates: `{payload['decision']['passing_candidate_count']}`",
        f"- Selected candidate: `{payload['decision']['selected_policy']}`",
        f"- Fee: `{FEE_BPS}` bps",
        f"- Gate: selector and holdout total PnL > 0, win rate > {MIN_WIN_RATE:.2%}, average trades/day >= {MIN_AVG_TRADES_PER_CALENDAR_DAY}, calendar-positive months >= {MIN_CALENDAR_POSITIVE_MONTH_RATE:.2%}",
        "",
        "## Top Candidates",
        "",
        top[report_cols].to_csv(index=False).strip() if not top.empty else "No candidates were produced.",
        "",
        "## Passing Candidates",
        "",
        passed[report_cols].to_csv(index=False).strip() if not passed.empty else "No candidate passed the thick-edge gate.",
        "",
        "## Interpretation",
        "",
        "V101 replaces direction-probability selection with future-return regression. It only trades when predicted return magnitude exceeds a fixed edge threshold and evaluates the result after the existing 8.5 bps round-trip cost. This is a research scan, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    bars = v94._full_bars()
    candidates, ledgers, metas = _scan(bars)
    passed = candidates.loc[candidates["passed_thick_edge_gate"]].copy() if not candidates.empty else pd.DataFrame()

    candidates_path = OUT_DIR / "v101_thick_edge_candidates.csv"
    passed_path = OUT_DIR / "v101_thick_edge_passed_candidates.csv"
    candidates.to_csv(candidates_path, index=False)
    passed.to_csv(passed_path, index=False)
    for policy_id, ledger in ledgers.items():
        ledger.to_csv(OUT_DIR / f"v101_{policy_id}_trade_ledger.csv", index=False)

    selected = str(passed.iloc[0]["policy_id"]) if not passed.empty else None
    payload = {
        "version": "v101_btcusdc_thick_edge_regression",
        "scan": {
            "candidate_count": int(len(candidates)),
            "horizons": list(HORIZONS),
            "edge_thresholds_bps": list(EDGE_THRESHOLDS_BPS),
            "fee_bps": float(FEE_BPS),
            "sample_every_minutes": v96.SAMPLE_EVERY_MINUTES,
            "selector_days": v96.SELECTOR_DAYS,
            "holdout_days": v96.HOLDOUT_DAYS,
            "horizon_meta": metas,
        },
        "decision": {
            "passing_candidate_count": int(len(passed)),
            "selected_policy": selected,
            "goal_satisfied_by_scan": bool(selected is not None),
            "failed_reason": None if selected is not None else "no candidate passed the 8.5 bps thick-edge high-frequency gate",
        },
        "outputs": {
            "candidates": str(candidates_path),
            "passed_candidates": str(passed_path),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v101_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload, candidates, passed)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
