from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_btcusdc_v94_high_frequency_scan as v94
import run_btcusdc_v96_ml_probability_gate as v96
import run_btcusdc_v101_thick_edge_regression as v101
import run_btcusdc_v102_ma_feature_regression as v102


OUT_DIR = ROOT / "runs" / "research_v104_btcusdc_ma_hgb_daily_topk_classifier"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V104_BTCUSDC_MA_HGB_DAILY_TOPK_CLASSIFIER_RESULTS.md"

HORIZONS = (5, 10, 15, 30)
PROBABILITY_FLOORS = (0.34, 0.40, 0.45, 0.50, 0.55, 0.60)
DAILY_TOP_KS = (1, 2, 3)
FEE_BPS = v101.FEE_BPS

MIN_WIN_RATE = v101.MIN_WIN_RATE
MIN_AVG_TRADES_PER_CALENDAR_DAY = v101.MIN_AVG_TRADES_PER_CALENDAR_DAY
MIN_CALENDAR_POSITIVE_MONTH_RATE = v101.MIN_CALENDAR_POSITIVE_MONTH_RATE


def _fit_hgb_classifier(train: pd.DataFrame, feature_cols: list[str]):
    model = make_pipeline(
        SimpleImputer(strategy="median"),
        HistGradientBoostingClassifier(
            max_iter=120,
            learning_rate=0.04,
            max_leaf_nodes=15,
            l2_regularization=0.10,
            early_stopping=True,
            validation_fraction=0.15,
            random_state=26104,
        ),
    )
    model.fit(train[feature_cols], train["label"].astype(int))
    return model


def _probability_predictions(model, frame: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    return v96._probability_predictions(model, frame, feature_cols)


def _non_overlapping_probability_indices(day_frame: pd.DataFrame, *, daily_top_k: int, horizon_minutes: int) -> list[int]:
    ranked = day_frame.sort_values(["direction_probability", "timestamp"], ascending=[False, True])
    selected: list[int] = []
    selected_ts: list[pd.Timestamp] = []
    spacing = pd.Timedelta(minutes=int(horizon_minutes))
    for idx, row in ranked.iterrows():
        if len(selected) >= int(daily_top_k):
            break
        ts = pd.to_datetime(row["timestamp"], utc=True)
        if any(abs(ts - prev) < spacing for prev in selected_ts):
            continue
        selected.append(int(idx))
        selected_ts.append(ts)
    return selected


def _daily_topk_probability_ledger(
    predictions: pd.DataFrame,
    *,
    daily_top_k: int,
    probability_floor: float,
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
    frame = frame.loc[frame["direction_probability"] >= float(probability_floor)].copy()
    if frame.empty:
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
                "probability_floor",
                "horizon_minutes",
            ]
        )

    keep_idx: list[int] = []
    for _, day_frame in frame.groupby(frame["timestamp"].dt.normalize(), sort=True):
        keep_idx.extend(
            _non_overlapping_probability_indices(
                day_frame,
                daily_top_k=int(daily_top_k),
                horizon_minutes=int(horizon_minutes),
            )
        )
    if not keep_idx:
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
                "probability_floor",
                "horizon_minutes",
            ]
        )

    kept = frame.loc[keep_idx].copy().sort_values("timestamp").reset_index(drop=True)
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
            "probability_floor": float(probability_floor),
            "horizon_minutes": int(horizon_minutes),
        }
    )
    ledger["equity_bps"] = pd.to_numeric(ledger["net_pnl_bps"], errors="coerce").fillna(0.0).cumsum()
    return ledger


def _passes_daily_classifier_gate(row: dict[str, object]) -> bool:
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

    model = _fit_hgb_classifier(train, feature_cols)
    selector_pred = _probability_predictions(model, selector, feature_cols)
    holdout_pred = _probability_predictions(model, holdout, feature_cols)
    selector_start_ts = pd.to_datetime(selector["timestamp"].min(), utc=True)
    selector_end_ts = pd.to_datetime(selector["timestamp"].max(), utc=True)
    holdout_start_ts = pd.to_datetime(holdout["timestamp"].min(), utc=True)
    holdout_end_ts = pd.to_datetime(holdout["timestamp"].max(), utc=True)
    rows: list[dict[str, object]] = []
    ledgers: dict[str, pd.DataFrame] = {}

    for probability_floor in PROBABILITY_FLOORS:
        for daily_top_k in DAILY_TOP_KS:
            selector_ledger = _daily_topk_probability_ledger(
                selector_pred,
                daily_top_k=int(daily_top_k),
                probability_floor=float(probability_floor),
                horizon_minutes=int(horizon),
                fee_bps=FEE_BPS,
            )
            holdout_ledger = _daily_topk_probability_ledger(
                holdout_pred,
                daily_top_k=int(daily_top_k),
                probability_floor=float(probability_floor),
                horizon_minutes=int(horizon),
                fee_bps=FEE_BPS,
            )
            selector_summary = v94._trade_summary(selector_ledger, start_ts=selector_start_ts, end_ts=selector_end_ts)
            holdout_summary = v94._trade_summary(holdout_ledger, start_ts=holdout_start_ts, end_ts=holdout_end_ts)
            row = {
                "policy_id": f"hgb_ma_cls_top{int(daily_top_k)}_h{int(horizon)}_p{float(probability_floor):.2f}",
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
            row["passed_daily_classifier_gate"] = bool(_passes_daily_classifier_gate(row))
            rows.append(row)
            if bool(row["passed_daily_classifier_gate"]):
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
        print(f"evaluated MA HGB classifier horizon {horizon} with {len(horizon_rows)} policies", flush=True)
    candidates = pd.DataFrame(rows)
    if not candidates.empty:
        candidates = candidates.sort_values(
            [
                "passed_daily_classifier_gate",
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
        "passed_daily_classifier_gate",
        "horizon_minutes",
        "daily_top_k",
        "probability_floor",
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
        "# Research V104 BTCUSDC MA HGB Daily Top-K Classifier Results",
        "",
        "## Decision",
        "",
        f"- Evaluated candidates: `{payload['scan']['candidate_count']}`",
        f"- Passing MA HGB classifier candidates: `{payload['decision']['passing_candidate_count']}`",
        f"- Selected candidate: `{payload['decision']['selected_policy']}`",
        f"- Fee: `{FEE_BPS}` bps",
        f"- Horizons: `{list(HORIZONS)}`",
        f"- Daily top-k values: `{list(DAILY_TOP_KS)}`",
        f"- Probability floors: `{list(PROBABILITY_FLOORS)}`",
        "",
        "## Top Candidates",
        "",
        top[report_cols].to_csv(index=False).strip() if not top.empty else "No candidates were produced.",
        "",
        "## Passing Candidates",
        "",
        passed[report_cols].to_csv(index=False).strip() if not passed.empty else "No candidate passed the MA HGB daily top-k classifier gate.",
        "",
        "## Interpretation",
        "",
        "V104 trains a MA-feature HGB classifier to predict fee-aware down, flat, and up labels, then selects the most confident non-overlapping direction predictions per UTC day. This is a research scan, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    bars = v94._full_bars()
    candidates, ledgers, metas = _scan(bars)
    passed = candidates.loc[candidates["passed_daily_classifier_gate"]].copy() if not candidates.empty else pd.DataFrame()

    candidates_path = OUT_DIR / "v104_ma_hgb_daily_topk_candidates.csv"
    passed_path = OUT_DIR / "v104_ma_hgb_daily_topk_passed_candidates.csv"
    candidates.to_csv(candidates_path, index=False)
    passed.to_csv(passed_path, index=False)
    for policy_id, ledger in ledgers.items():
        ledger.to_csv(OUT_DIR / f"v104_{policy_id}_trade_ledger.csv", index=False)

    selected = str(passed.iloc[0]["policy_id"]) if not passed.empty else None
    payload = {
        "version": "v104_btcusdc_ma_hgb_daily_topk_classifier",
        "scan": {
            "candidate_count": int(len(candidates)),
            "horizons": list(HORIZONS),
            "daily_top_ks": list(DAILY_TOP_KS),
            "probability_floors": list(PROBABILITY_FLOORS),
            "fee_bps": float(FEE_BPS),
            "ma_windows": list(v102.MA_WINDOWS),
            "ma_feature_columns": list(v102.MA_FEATURE_COLUMNS),
            "sample_every_minutes": v96.SAMPLE_EVERY_MINUTES,
            "selector_days": v96.SELECTOR_DAYS,
            "holdout_days": v96.HOLDOUT_DAYS,
            "horizon_meta": metas,
        },
        "decision": {
            "passing_candidate_count": int(len(passed)),
            "selected_policy": selected,
            "goal_satisfied_by_scan": bool(selected is not None),
            "failed_reason": None if selected is not None else "no candidate passed the 8.5 bps MA HGB daily top-k classifier gate",
        },
        "outputs": {
            "candidates": str(candidates_path),
            "passed_candidates": str(passed_path),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v104_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload, candidates, passed)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
