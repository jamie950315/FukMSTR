from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_btcusdc_v94_high_frequency_scan as v94


OUT_DIR = ROOT / "runs" / "research_v96_btcusdc_ml_probability_gate"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V96_BTCUSDC_ML_PROBABILITY_GATE_RESULTS.md"

HORIZONS = (30, 60, 120)
PROBABILITY_THRESHOLDS = (0.40, 0.45, 0.50, 0.55, 0.60, 0.65)
FEE_BPS = 8.5
SAMPLE_EVERY_MINUTES = 5
SELECTOR_DAYS = 120
HOLDOUT_DAYS = 365

MIN_WIN_RATE = 0.55
MIN_AVG_TRADES_PER_CALENDAR_DAY = 1.0
MIN_CALENDAR_POSITIVE_MONTH_RATE = 0.50


def _labels_from_future_return(future_return_bps: pd.Series, *, fee_bps: float) -> pd.Series:
    future = pd.to_numeric(future_return_bps, errors="coerce").fillna(0.0)
    labels = pd.Series(0, index=future.index, dtype=int)
    labels.loc[future > float(fee_bps)] = 1
    labels.loc[future < -float(fee_bps)] = -1
    return labels


def _feature_frame(bars: pd.DataFrame, *, horizon_minutes: int) -> tuple[pd.DataFrame, list[str]]:
    source = bars.copy().sort_values("timestamp").reset_index(drop=True)
    source["timestamp"] = pd.to_datetime(source["timestamp"], utc=True)
    open_px = pd.to_numeric(source["open"], errors="coerce")
    high = pd.to_numeric(source["high"], errors="coerce")
    low = pd.to_numeric(source["low"], errors="coerce")
    close = pd.to_numeric(source["close"], errors="coerce")
    volume = pd.to_numeric(source["volume"], errors="coerce").replace(0.0, np.nan)
    flow = pd.to_numeric(source.get("signed_taker_imbalance", pd.Series(0.0, index=source.index)), errors="coerce")

    features = pd.DataFrame({"timestamp": source["timestamp"], "open": open_px})
    for lookback in (1, 3, 5, 15, 30, 60, 120, 240):
        lb = int(lookback)
        ret = open_px.pct_change(lb) * 10000.0
        features[f"ret_{lb}"] = ret
        features[f"absret_mean_{lb}"] = ret.abs().rolling(lb, min_periods=max(1, lb // 4)).mean()
        features[f"volume_ratio_{lb}"] = volume / volume.rolling(lb, min_periods=max(1, lb // 4)).mean()
    features["bar_range_bps"] = (high - low) / close * 10000.0
    for lookback in (5, 15, 60, 240):
        lb = int(lookback)
        features[f"flow_mean_{lb}"] = flow.shift(1).rolling(lb, min_periods=max(1, lb // 4)).mean()
        features[f"abs_flow_mean_{lb}"] = features[f"flow_mean_{lb}"].abs()
        features[f"range_mean_{lb}"] = features["bar_range_bps"].rolling(lb, min_periods=max(1, lb // 4)).mean()
    features["hour"] = source["timestamp"].dt.hour.astype(float)
    features["dow"] = source["timestamp"].dt.dayofweek.astype(float)
    features["future_return_bps"] = (open_px.shift(-int(horizon_minutes)) / open_px - 1.0) * 10000.0
    features["label"] = _labels_from_future_return(features["future_return_bps"], fee_bps=FEE_BPS)

    sampled = features.loc[features["timestamp"].dt.minute.mod(SAMPLE_EVERY_MINUTES) == 0].copy()
    feature_cols = [c for c in sampled.columns if c not in {"timestamp", "open", "future_return_bps", "label"}]
    sampled[feature_cols] = sampled[feature_cols].replace([np.inf, -np.inf], np.nan)
    return sampled.dropna(subset=["timestamp", "future_return_bps"]).reset_index(drop=True), feature_cols


def _prediction_ledger(predictions: pd.DataFrame, *, probability_threshold: float, horizon_minutes: int, fee_bps: float) -> pd.DataFrame:
    frame = predictions.copy()
    up = pd.to_numeric(frame["prob_up"], errors="coerce").fillna(0.0)
    down = pd.to_numeric(frame["prob_down"], errors="coerce").fillna(0.0)
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[(up >= down) & (up >= float(probability_threshold))] = 1
    signal.loc[(down > up) & (down >= float(probability_threshold))] = -1
    eligible = signal != 0
    keep_idx = v94._spaced_indices(eligible, horizon=int(horizon_minutes))
    if keep_idx.size == 0:
        return pd.DataFrame(columns=["timestamp", "signal", "future_return_bps", "net_pnl_bps", "probability_threshold", "horizon_minutes"])
    kept = frame.iloc[keep_idx].copy()
    kept_signal = signal.iloc[keep_idx].astype(int).to_numpy()
    future = pd.to_numeric(kept["future_return_bps"], errors="coerce").fillna(0.0).to_numpy(float)
    ledger = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(kept["timestamp"], utc=True).to_numpy(),
            "signal": kept_signal,
            "future_return_bps": future,
            "prob_up": pd.to_numeric(kept["prob_up"], errors="coerce").fillna(0.0).to_numpy(float),
            "prob_down": pd.to_numeric(kept["prob_down"], errors="coerce").fillna(0.0).to_numpy(float),
            "gross_pnl_bps": future * kept_signal,
            "net_pnl_bps": future * kept_signal - float(fee_bps),
            "probability_threshold": float(probability_threshold),
            "horizon_minutes": int(horizon_minutes),
        }
    )
    ledger["equity_bps"] = pd.to_numeric(ledger["net_pnl_bps"], errors="coerce").fillna(0.0).cumsum()
    return ledger


def _passes_ml_gate(row: dict[str, object]) -> bool:
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


def _probability_predictions(model, frame: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    proba = model.predict_proba(frame[feature_cols])
    classes = list(model.classes_)
    out = frame[["timestamp", "future_return_bps"]].copy()
    for label, name in [(-1, "prob_down"), (0, "prob_flat"), (1, "prob_up")]:
        out[name] = proba[:, classes.index(label)] if label in classes else 0.0
    return out


def _fit_model(train: pd.DataFrame, feature_cols: list[str]):
    model = make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        LogisticRegression(max_iter=250, class_weight="balanced", random_state=26096),
    )
    model.fit(train[feature_cols], train["label"].astype(int))
    return model


def _evaluate_horizon(bars: pd.DataFrame, *, horizon: int) -> tuple[list[dict[str, object]], dict[str, pd.DataFrame], dict[str, object]]:
    data, feature_cols = _feature_frame(bars, horizon_minutes=int(horizon))
    full_end = pd.to_datetime(data["timestamp"].max(), utc=True)
    holdout_start = full_end - pd.Timedelta(days=HOLDOUT_DAYS)
    selector_start = holdout_start - pd.Timedelta(days=SELECTOR_DAYS)
    train = data.loc[data["timestamp"] < selector_start].copy()
    selector = data.loc[(data["timestamp"] >= selector_start) & (data["timestamp"] < holdout_start)].copy()
    holdout = data.loc[data["timestamp"] >= holdout_start].copy()
    if len(train) < 1000 or len(selector) < 100 or len(holdout) < 100:
        return [], {}, {"horizon_minutes": int(horizon), "skipped": True, "reason": "insufficient rows"}

    model = _fit_model(train, feature_cols)
    selector_pred = _probability_predictions(model, selector, feature_cols)
    holdout_pred = _probability_predictions(model, holdout, feature_cols)
    rows: list[dict[str, object]] = []
    ledgers: dict[str, pd.DataFrame] = {}
    selector_start_ts = pd.to_datetime(selector["timestamp"].min(), utc=True)
    selector_end_ts = pd.to_datetime(selector["timestamp"].max(), utc=True)
    holdout_start_ts = pd.to_datetime(holdout["timestamp"].min(), utc=True)
    holdout_end_ts = pd.to_datetime(holdout["timestamp"].max(), utc=True)

    for threshold in PROBABILITY_THRESHOLDS:
        selector_ledger = _prediction_ledger(selector_pred, probability_threshold=float(threshold), horizon_minutes=int(horizon), fee_bps=FEE_BPS)
        holdout_ledger = _prediction_ledger(holdout_pred, probability_threshold=float(threshold), horizon_minutes=int(horizon), fee_bps=FEE_BPS)
        selector_summary = v94._trade_summary(selector_ledger, start_ts=selector_start_ts, end_ts=selector_end_ts)
        holdout_summary = v94._trade_summary(holdout_ledger, start_ts=holdout_start_ts, end_ts=holdout_end_ts)
        row = {
            "policy_id": f"ml_logistic_h{int(horizon)}_p{float(threshold):.2f}",
            "horizon_minutes": int(horizon),
            "probability_threshold": float(threshold),
            "train_rows": int(len(train)),
            "selector_rows": int(len(selector)),
            "holdout_rows": int(len(holdout)),
            **{f"selector_{key}": value for key, value in selector_summary.items()},
            **{f"holdout_{key}": value for key, value in holdout_summary.items()},
        }
        row["passed_ml_gate"] = bool(_passes_ml_gate(row))
        rows.append(row)
        if bool(row["passed_ml_gate"]):
            ledgers[str(row["policy_id"])] = pd.concat([selector_ledger.assign(window="selector"), holdout_ledger.assign(window="holdout")], ignore_index=True)
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
        print(f"evaluated ML horizon {horizon} with {len(horizon_rows)} thresholds", flush=True)
    candidates = pd.DataFrame(rows)
    if not candidates.empty:
        candidates = candidates.sort_values(
            [
                "passed_ml_gate",
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
        "passed_ml_gate",
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
    top = candidates.head(10).copy() if not candidates.empty else pd.DataFrame()
    lines = [
        "# Research V96 BTCUSDC ML Probability Gate Results",
        "",
        "## Decision",
        "",
        f"- Evaluated candidates: `{payload['scan']['candidate_count']}`",
        f"- Passing ML candidates: `{payload['decision']['passing_candidate_count']}`",
        f"- Selected candidate: `{payload['decision']['selected_policy']}`",
        f"- Gate: selector and holdout total PnL > 0, win rate > {MIN_WIN_RATE:.2%}, average trades/day >= {MIN_AVG_TRADES_PER_CALENDAR_DAY}, calendar-positive months >= {MIN_CALENDAR_POSITIVE_MONTH_RATE:.2%}",
        "",
        "## Top Candidates",
        "",
        top[report_cols].to_csv(index=False).strip() if not top.empty else "No candidates were produced.",
        "",
        "## Passing Candidates",
        "",
        passed[report_cols].to_csv(index=False).strip() if not passed.empty else "No candidate passed the ML probability gate.",
        "",
        "## Interpretation",
        "",
        "V96 trains a logistic probability model on sampled BTCUSDC 1m aggTrade flow bars. The model is trained before the selector window; probability thresholds are evaluated on selector and holdout windows. This is a research scan, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    bars = v94._full_bars()
    candidates, ledgers, metas = _scan(bars)
    passed = candidates.loc[candidates["passed_ml_gate"]].copy() if not candidates.empty else pd.DataFrame()

    candidates_path = OUT_DIR / "v96_ml_probability_candidates.csv"
    passed_path = OUT_DIR / "v96_ml_probability_passed_candidates.csv"
    candidates.to_csv(candidates_path, index=False)
    passed.to_csv(passed_path, index=False)
    for policy_id, ledger in ledgers.items():
        ledger.to_csv(OUT_DIR / f"v96_{policy_id}_trade_ledger.csv", index=False)

    selected = str(passed.iloc[0]["policy_id"]) if not passed.empty else None
    payload = {
        "version": "v96_btcusdc_ml_probability_gate",
        "scan": {
            "candidate_count": int(len(candidates)),
            "horizons": list(HORIZONS),
            "probability_thresholds": list(PROBABILITY_THRESHOLDS),
            "fee_bps": FEE_BPS,
            "sample_every_minutes": SAMPLE_EVERY_MINUTES,
            "selector_days": SELECTOR_DAYS,
            "holdout_days": HOLDOUT_DAYS,
            "horizon_meta": metas,
        },
        "decision": {
            "passing_candidate_count": int(len(passed)),
            "selected_policy": selected,
            "goal_satisfied_by_scan": bool(selected is not None),
            "failed_reason": None if selected is not None else "no candidate passed the ML probability profitability, win-rate, frequency, and month-stability gate",
        },
        "outputs": {
            "candidates": str(candidates_path),
            "passed_candidates": str(passed_path),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v96_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload, candidates, passed)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
