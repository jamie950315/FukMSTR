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


OUT_DIR = ROOT / "runs" / "research_v97_btcusdc_hgb_regime_gate"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V97_BTCUSDC_HGB_REGIME_GATE_RESULTS.md"

HORIZONS = (30, 60, 120)
PROBABILITY_THRESHOLDS = (0.35, 0.40, 0.45, 0.50, 0.55)
REGIME_QUANTILES = (0.0, 0.5, 0.75)
FEE_BPS = 8.5
MIN_WIN_RATE = 0.55
MIN_AVG_TRADES_PER_CALENDAR_DAY = 1.0
MIN_CALENDAR_POSITIVE_MONTH_RATE = 0.50


def _regime_mask(
    frame: pd.DataFrame,
    selector_reference: pd.DataFrame,
    *,
    range_quantile: float,
    flow_quantile: float,
) -> pd.Series:
    mask = pd.Series(True, index=frame.index)
    if "range_mean_60" in frame.columns and "range_mean_60" in selector_reference.columns:
        range_threshold = float(pd.to_numeric(selector_reference["range_mean_60"], errors="coerce").dropna().quantile(float(range_quantile)))
        mask &= pd.to_numeric(frame["range_mean_60"], errors="coerce").fillna(-np.inf) >= range_threshold
    if "abs_flow_mean_60" in frame.columns and "abs_flow_mean_60" in selector_reference.columns:
        flow_threshold = float(pd.to_numeric(selector_reference["abs_flow_mean_60"], errors="coerce").dropna().quantile(float(flow_quantile)))
        mask &= pd.to_numeric(frame["abs_flow_mean_60"], errors="coerce").fillna(-np.inf) >= flow_threshold
    return mask


def _passes_tree_gate(row: dict[str, object]) -> bool:
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


def _fit_hgb(train: pd.DataFrame, feature_cols: list[str]):
    model = make_pipeline(
        SimpleImputer(strategy="median"),
        HistGradientBoostingClassifier(
            max_iter=80,
            learning_rate=0.05,
            max_leaf_nodes=15,
            l2_regularization=0.10,
            early_stopping=True,
            validation_fraction=0.15,
            random_state=26097,
        ),
    )
    model.fit(train[feature_cols], train["label"].astype(int))
    return model


def _prediction_frame(model, frame: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    pred = v96._probability_predictions(model, frame, feature_cols)
    for column in ("range_mean_60", "abs_flow_mean_60", "bar_range_bps", "hour"):
        if column in frame.columns:
            pred[column] = pd.to_numeric(frame[column], errors="coerce").to_numpy(float)
    return pred


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

    model = _fit_hgb(train, feature_cols)
    selector_pred = _prediction_frame(model, selector, feature_cols)
    holdout_pred = _prediction_frame(model, holdout, feature_cols)
    selector_start_ts = pd.to_datetime(selector["timestamp"].min(), utc=True)
    selector_end_ts = pd.to_datetime(selector["timestamp"].max(), utc=True)
    holdout_start_ts = pd.to_datetime(holdout["timestamp"].min(), utc=True)
    holdout_end_ts = pd.to_datetime(holdout["timestamp"].max(), utc=True)
    rows: list[dict[str, object]] = []
    ledgers: dict[str, pd.DataFrame] = {}

    for probability_threshold in PROBABILITY_THRESHOLDS:
        for range_quantile in REGIME_QUANTILES:
            for flow_quantile in REGIME_QUANTILES:
                selector_mask = _regime_mask(selector_pred, selector_pred, range_quantile=float(range_quantile), flow_quantile=float(flow_quantile))
                holdout_mask = _regime_mask(holdout_pred, selector_pred, range_quantile=float(range_quantile), flow_quantile=float(flow_quantile))
                selector_ledger = v96._prediction_ledger(
                    selector_pred.loc[selector_mask].copy(),
                    probability_threshold=float(probability_threshold),
                    horizon_minutes=int(horizon),
                    fee_bps=FEE_BPS,
                )
                holdout_ledger = v96._prediction_ledger(
                    holdout_pred.loc[holdout_mask].copy(),
                    probability_threshold=float(probability_threshold),
                    horizon_minutes=int(horizon),
                    fee_bps=FEE_BPS,
                )
                selector_summary = v94._trade_summary(selector_ledger, start_ts=selector_start_ts, end_ts=selector_end_ts)
                holdout_summary = v94._trade_summary(holdout_ledger, start_ts=holdout_start_ts, end_ts=holdout_end_ts)
                row = {
                    "policy_id": f"hgb_h{int(horizon)}_p{float(probability_threshold):.2f}_rq{float(range_quantile):.2f}_fq{float(flow_quantile):.2f}",
                    "horizon_minutes": int(horizon),
                    "probability_threshold": float(probability_threshold),
                    "range_quantile": float(range_quantile),
                    "flow_quantile": float(flow_quantile),
                    "train_rows": int(len(train)),
                    "selector_rows": int(len(selector)),
                    "holdout_rows": int(len(holdout)),
                    **{f"selector_{key}": value for key, value in selector_summary.items()},
                    **{f"holdout_{key}": value for key, value in holdout_summary.items()},
                }
                row["passed_tree_gate"] = bool(_passes_tree_gate(row))
                rows.append(row)
                if bool(row["passed_tree_gate"]):
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
        print(f"evaluated HGB horizon {horizon} with {len(horizon_rows)} candidates", flush=True)
    candidates = pd.DataFrame(rows)
    if not candidates.empty:
        candidates = candidates.sort_values(
            [
                "passed_tree_gate",
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
        "passed_tree_gate",
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
        "# Research V97 BTCUSDC HGB Regime Gate Results",
        "",
        "## Decision",
        "",
        f"- Evaluated candidates: `{payload['scan']['candidate_count']}`",
        f"- Passing HGB regime candidates: `{payload['decision']['passing_candidate_count']}`",
        f"- Selected candidate: `{payload['decision']['selected_policy']}`",
        f"- Gate: selector and holdout total PnL > 0, win rate > {MIN_WIN_RATE:.2%}, average trades/day >= {MIN_AVG_TRADES_PER_CALENDAR_DAY}, calendar-positive months >= {MIN_CALENDAR_POSITIVE_MONTH_RATE:.2%}",
        "",
        "## Top Candidates",
        "",
        top[report_cols].to_csv(index=False).strip() if not top.empty else "No candidates were produced.",
        "",
        "## Passing Candidates",
        "",
        passed[report_cols].to_csv(index=False).strip() if not passed.empty else "No candidate passed the HGB regime gate.",
        "",
        "## Interpretation",
        "",
        "V97 trains an HGB classifier on sampled BTCUSDC 1m aggTrade flow bars and applies selector-only regime gates. Probability and regime thresholds are evaluated on selector and holdout windows. This is a research scan, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    bars = v94._full_bars()
    candidates, ledgers, metas = _scan(bars)
    passed = candidates.loc[candidates["passed_tree_gate"]].copy() if not candidates.empty else pd.DataFrame()

    candidates_path = OUT_DIR / "v97_hgb_regime_candidates.csv"
    passed_path = OUT_DIR / "v97_hgb_regime_passed_candidates.csv"
    candidates.to_csv(candidates_path, index=False)
    passed.to_csv(passed_path, index=False)
    for policy_id, ledger in ledgers.items():
        ledger.to_csv(OUT_DIR / f"v97_{policy_id}_trade_ledger.csv", index=False)

    selected = str(passed.iloc[0]["policy_id"]) if not passed.empty else None
    payload = {
        "version": "v97_btcusdc_hgb_regime_gate",
        "scan": {
            "candidate_count": int(len(candidates)),
            "horizons": list(HORIZONS),
            "probability_thresholds": list(PROBABILITY_THRESHOLDS),
            "regime_quantiles": list(REGIME_QUANTILES),
            "fee_bps": FEE_BPS,
            "sample_every_minutes": v96.SAMPLE_EVERY_MINUTES,
            "selector_days": v96.SELECTOR_DAYS,
            "holdout_days": v96.HOLDOUT_DAYS,
            "horizon_meta": metas,
        },
        "decision": {
            "passing_candidate_count": int(len(passed)),
            "selected_policy": selected,
            "goal_satisfied_by_scan": bool(selected is not None),
            "failed_reason": None if selected is not None else "no candidate passed the HGB regime profitability, win-rate, frequency, and month-stability gate",
        },
        "outputs": {
            "candidates": str(candidates_path),
            "passed_candidates": str(passed_path),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v97_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload, candidates, passed)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
