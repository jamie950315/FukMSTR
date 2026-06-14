from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import backtest_predictions, backtest_predictions_non_overlapping, sweep_edge_thresholds
from .config import AppConfig
from .data_schema import read_csv, timestamps_to_ns
from .features import build_features
from .labels import add_future_labels
from .models import (
    evaluate_classification,
    evaluate_probabilities,
    feature_importance_frame,
    predict_frame,
    select_feature_columns,
    train_model,
)
from .pipeline import _label_distribution


@dataclass(frozen=True)
class WalkForwardFold:
    fold: int
    train_start: int
    train_end: int
    valid_start: int
    valid_end: int

    @property
    def train_rows(self) -> int:
        return max(0, self.train_end - self.train_start)

    @property
    def valid_rows(self) -> int:
        return max(0, self.valid_end - self.valid_start)


def make_walk_forward_folds(
    n_rows: int,
    folds: int = 3,
    min_train_ratio: float = 0.50,
    valid_ratio: float = 0.15,
    embargo_rows: int = 0,
) -> list[WalkForwardFold]:
    if n_rows < 300:
        raise ValueError(f"walk-forward needs at least 300 rows, got {n_rows}")
    if folds < 1:
        raise ValueError("folds must be >= 1")
    min_train = max(100, int(n_rows * min_train_ratio))
    valid_size = max(50, int(n_rows * valid_ratio))
    available = n_rows - min_train - valid_size
    if available < 0:
        valid_size = max(50, n_rows - min_train)
        available = n_rows - min_train - valid_size
    step = max(1, available // max(folds - 1, 1)) if folds > 1 else 1
    out: list[WalkForwardFold] = []
    for i in range(folds):
        valid_start = min_train + i * step
        valid_end = min(valid_start + valid_size, n_rows)
        train_end = max(0, valid_start - embargo_rows)
        if train_end < 100 or valid_end - valid_start < 50:
            continue
        out.append(WalkForwardFold(i + 1, 0, train_end, valid_start, valid_end))
    return out


def infer_median_step_sec(timestamps: pd.Series) -> float:
    ns = timestamps_to_ns(timestamps)
    if len(ns) < 2:
        return 0.0
    diff = np.diff(ns)
    diff = diff[diff > 0]
    if len(diff) == 0:
        return 0.0
    return float(np.median(diff) / 1_000_000_000)


def seconds_to_rows(timestamps: pd.Series, seconds: float) -> int:
    step = infer_median_step_sec(timestamps)
    if step <= 0:
        return 0
    return int(math.ceil(float(seconds) / step))


def run_walk_forward(
    *,
    book_path: str | Path,
    trades_path: str | Path | None,
    base_config_path: str | Path | None,
    out_dir: str | Path,
    horizon_sec: float,
    threshold_bps: float,
    model_type: str,
    edge_threshold: float,
    folds: int = 3,
    min_train_ratio: float = 0.50,
    valid_ratio: float = 0.15,
    embargo_sec: float | None = None,
    edge_thresholds: list[float] | None = None,
    run_null: bool = True,
    clean: bool = False,
) -> dict[str, object]:
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    cfg = AppConfig.from_yaml(base_config_path)
    cfg.labels.horizon_sec = float(horizon_sec)
    cfg.labels.threshold_bps = float(threshold_bps)
    cfg.model.type = str(model_type)
    cfg.backtest.signal_edge_threshold = float(edge_threshold)

    book = read_csv(book_path)
    trades = read_csv(trades_path) if trades_path else None
    features = build_features(book, trades=trades, cfg=cfg.features, timestamp_col=cfg.io.timestamp_col)
    dataset = add_future_labels(features, horizon_sec=cfg.labels.horizon_sec, threshold_bps=cfg.labels.threshold_bps)
    if len(dataset) < 300:
        raise ValueError(f"dataset too small after feature/label construction: {len(dataset)} rows")

    embargo = cfg.labels.horizon_sec if embargo_sec is None else float(embargo_sec)
    embargo_rows = seconds_to_rows(dataset["timestamp"], embargo)
    fold_defs = make_walk_forward_folds(
        len(dataset),
        folds=int(folds),
        min_train_ratio=float(min_train_ratio),
        valid_ratio=float(valid_ratio),
        embargo_rows=embargo_rows,
    )
    if not fold_defs:
        raise ValueError("no valid walk-forward folds created")

    feature_columns = select_feature_columns(dataset)
    fold_records: list[dict[str, object]] = []
    null_records: list[dict[str, object]] = []
    all_predictions: list[pd.DataFrame] = []
    all_importance: list[pd.DataFrame] = []
    rng = np.random.default_rng(cfg.model.random_state)

    for fold in fold_defs:
        fold_dir = out / f"fold_{fold.fold:02d}"
        fold_dir.mkdir(exist_ok=True)
        train_df = dataset.iloc[fold.train_start : fold.train_end].copy()
        valid_df = dataset.iloc[fold.valid_start : fold.valid_end].copy()
        X_train = train_df[feature_columns]
        y_train = train_df["label"]
        X_valid = valid_df[feature_columns]
        y_valid = valid_df["label"]

        model = train_model(X_train, y_train, cfg.model)
        meta_cols = _prediction_meta_columns(valid_df)
        pred = predict_frame(model, X_valid, valid_df[meta_cols])
        pred.insert(0, "fold", fold.fold)
        metrics = evaluate_classification(y_valid, pred["pred_label"])
        prob_metrics = evaluate_probabilities(y_valid, pred)
        _, bt = backtest_predictions(pred, cost_bps=cfg.backtest.cost_bps, edge_threshold=cfg.backtest.signal_edge_threshold)
        _, strict_bt = backtest_predictions_non_overlapping(
            pred,
            cost_bps=cfg.backtest.cost_bps,
            edge_threshold=cfg.backtest.signal_edge_threshold,
            horizon_sec=cfg.labels.horizon_sec,
        )
        importance = feature_importance_frame(model, feature_columns, top_n=50)
        if not importance.empty:
            importance.insert(0, "fold", fold.fold)
            all_importance.append(importance)

        pred.to_csv(fold_dir / "predictions_valid.csv", index=False)
        importance.to_csv(fold_dir / "feature_importance.csv", index=False)
        all_predictions.append(pred)
        record = _fold_record(fold, metrics, prob_metrics, bt, strict_bt, train_df, valid_df)
        fold_records.append(record)

        if run_null:
            null_model = train_model(X_train, pd.Series(rng.permutation(y_train.to_numpy()), index=y_train.index), cfg.model)
            null_pred = predict_frame(null_model, X_valid, valid_df[meta_cols])
            null_metrics = evaluate_classification(y_valid, null_pred["pred_label"])
            _, null_bt = backtest_predictions(null_pred, cost_bps=cfg.backtest.cost_bps, edge_threshold=cfg.backtest.signal_edge_threshold)
            null_records.append(_null_record(fold.fold, null_metrics, null_bt))

    folds_df = pd.DataFrame(fold_records)
    folds_df.to_csv(out / "fold_metrics.csv", index=False)
    if null_records:
        pd.DataFrame(null_records).to_csv(out / "null_shuffle_metrics.csv", index=False)

    oof = pd.concat(all_predictions, ignore_index=True)
    oof.to_csv(out / "oof_predictions.csv", index=False)
    if all_importance:
        importance_df = pd.concat(all_importance, ignore_index=True)
        importance_df.to_csv(out / "feature_importance_by_fold.csv", index=False)
        top_importance = summarize_importance(importance_df)
        top_importance.to_csv(out / "feature_importance_mean.csv", index=False)
    else:
        top_importance = pd.DataFrame(columns=["feature", "importance_mean", "importance_std", "fold_count"])
        top_importance.to_csv(out / "feature_importance_mean.csv", index=False)

    thresholds = edge_thresholds or [0.05, 0.10, 0.20, 0.30, 0.50, 0.70, 0.90]
    edge_sweep = sweep_edge_thresholds(oof, cost_bps=cfg.backtest.cost_bps, thresholds=thresholds, horizon_sec=cfg.labels.horizon_sec)
    edge_sweep.to_csv(out / "edge_sweep_oof.csv", index=False)

    aggregate = aggregate_walk_forward(folds_df, edge_sweep, pd.DataFrame(null_records), top_importance)
    result = {
        "book_path": str(book_path),
        "trades_path": str(trades_path) if trades_path else None,
        "rows_features": int(len(features)),
        "rows_dataset": int(len(dataset)),
        "feature_count": int(len(feature_columns)),
        "median_step_sec": infer_median_step_sec(dataset["timestamp"]),
        "embargo_rows": int(embargo_rows),
        "config": cfg.to_dict(),
        "folds": [fold.__dict__ for fold in fold_defs],
        "aggregate": aggregate,
    }
    cfg.to_yaml(out / "config_resolved.yaml")
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_walk_forward_report(out / "REPORT.md", result, folds_df, edge_sweep, pd.DataFrame(null_records), top_importance)
    return result


def summarize_importance(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["feature", "importance_mean", "importance_std", "fold_count"])
    out = (
        frame.groupby("feature")["importance"]
        .agg(importance_mean="mean", importance_std="std", fold_count="count")
        .reset_index()
        .sort_values("importance_mean", ascending=False)
        .reset_index(drop=True)
    )
    return out


def aggregate_walk_forward(
    folds_df: pd.DataFrame,
    edge_sweep: pd.DataFrame,
    null_df: pd.DataFrame,
    importance: pd.DataFrame,
) -> dict[str, object]:
    out: dict[str, object] = {}
    metric_cols = [
        "accuracy",
        "balanced_accuracy",
        "macro_f1",
        "log_loss",
        "ece_pred_label",
        "event_mean_net_pnl_bps",
        "event_total_net_pnl_bps",
        "strict_mean_net_pnl_bps",
        "strict_total_net_pnl_bps",
    ]
    for col in metric_cols:
        if col in folds_df.columns:
            out[f"{col}_mean"] = _finite_mean(folds_df[col])
            out[f"{col}_std"] = _finite_std(folds_df[col])
    if not edge_sweep.empty:
        best_event = edge_sweep[edge_sweep["mode"] == "event"].head(1)
        best_strict = edge_sweep[edge_sweep["mode"] == "non_overlap"].head(1)
        out["best_event_edge"] = best_event.to_dict(orient="records")[0] if not best_event.empty else None
        out["best_non_overlap_edge"] = best_strict.to_dict(orient="records")[0] if not best_strict.empty else None
    if not null_df.empty and "balanced_accuracy" in null_df.columns:
        out["null_balanced_accuracy_mean"] = _finite_mean(null_df["balanced_accuracy"])
        out["signal_lift_vs_null_balanced_accuracy"] = out.get("balanced_accuracy_mean", 0.0) - out["null_balanced_accuracy_mean"]
    if not importance.empty:
        out["top_features"] = importance.head(15).to_dict(orient="records")
    return out


def write_walk_forward_report(
    path: str | Path,
    result: dict[str, object],
    folds_df: pd.DataFrame,
    edge_sweep: pd.DataFrame,
    null_df: pd.DataFrame,
    importance: pd.DataFrame,
) -> None:
    aggregate = result.get("aggregate", {}) if isinstance(result.get("aggregate"), dict) else {}
    lines = [
        "# Walk-forward Research Report",
        "",
        f"Book path: `{result.get('book_path')}`",
        f"Rows after label construction: {result.get('rows_dataset')}",
        f"Feature count: {result.get('feature_count')}",
        f"Median sampling step seconds: {result.get('median_step_sec'):.6f}",
        f"Embargo rows: {result.get('embargo_rows')}",
        "",
        "## Fold metrics",
        "",
    ]
    display_cols = [
        "fold",
        "train_rows",
        "valid_rows",
        "accuracy",
        "balanced_accuracy",
        "macro_f1",
        "event_mean_net_pnl_bps",
        "event_total_net_pnl_bps",
        "strict_mean_net_pnl_bps",
        "strict_total_net_pnl_bps",
    ]
    existing = [c for c in display_cols if c in folds_df.columns]
    lines.append(folds_df[existing].to_markdown(index=False) if not folds_df.empty else "No folds.")
    lines.extend(["", "## Aggregate", "", "```json", json.dumps(aggregate, indent=2), "```", ""])
    if not edge_sweep.empty:
        cols = [
            "mode",
            "edge_threshold",
            "trades",
            "hit_rate",
            "mean_net_pnl_bps",
            "total_net_pnl_bps",
            "max_drawdown_bps",
            "rank_score",
        ]
        lines.extend(["## Edge sweep on out-of-fold predictions", "", edge_sweep[cols].head(14).to_markdown(index=False), ""])
    if not null_df.empty:
        cols = ["fold", "accuracy", "balanced_accuracy", "macro_f1", "event_mean_net_pnl_bps", "event_total_net_pnl_bps"]
        lines.extend(["## Null shuffled-label sanity check", "", null_df[cols].to_markdown(index=False), ""])
    if not importance.empty:
        lines.extend(["## Mean feature importance", "", importance.head(25).to_markdown(index=False), ""])
    lines.extend(
        [
            "## Notes",
            "",
            "This report uses chronological folds and an embargo before every validation window. The non-overlap backtest keeps at most one trade per horizon window and is the stricter triage metric for overlapping labels.",
            "",
        ]
    )
    Path(path).write_text("\n".join(lines), encoding="utf-8")



def _prediction_meta_columns(frame: pd.DataFrame) -> list[str]:
    base = ["timestamp", "best_bid", "best_ask", "mid", "future_best_bid", "future_best_ask", "future_mid", "future_return_bps", "label"]
    candidates = [
        "spread_bps",
        "microprice_dev_bps",
        "microprice_dev_bps_l3",
        "microprice_dev_bps_l5",
        "microprice_dev_bps_l10",
        "imbalance_l1",
        "imbalance_l3",
        "imbalance_l5",
        "imbalance_l10",
        "ofi_sum_l1_norm",
        "ofi_sum_l3_norm",
        "ofi_sum_l5_norm",
        "ofi_sum_l10_norm",
        "trade_imbalance_1s",
        "trade_imbalance_5s",
        "trade_imbalance_10s",
        "mid_vol_20r_bps",
        "mid_ret_20r_bps",
        "prob_confidence",
    ]
    return [c for c in base + candidates if c in frame.columns]

def _fold_record(
    fold: WalkForwardFold,
    metrics: dict[str, object],
    prob_metrics: dict[str, object],
    event_bt: dict[str, float],
    strict_bt: dict[str, float],
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
) -> dict[str, object]:
    return {
        "fold": fold.fold,
        "train_start": fold.train_start,
        "train_end": fold.train_end,
        "valid_start": fold.valid_start,
        "valid_end": fold.valid_end,
        "train_rows": fold.train_rows,
        "valid_rows": fold.valid_rows,
        "label_distribution_train": json.dumps(_label_distribution(train_df["label"]), sort_keys=True),
        "label_distribution_valid": json.dumps(_label_distribution(valid_df["label"]), sort_keys=True),
        "accuracy": _float(metrics.get("accuracy")),
        "balanced_accuracy": _float(metrics.get("balanced_accuracy")),
        "macro_f1": _float(metrics.get("macro_f1")),
        "majority_accuracy_valid": _float(metrics.get("majority_accuracy_valid")),
        "accuracy_lift_vs_majority": _float(metrics.get("accuracy_lift_vs_majority")),
        "log_loss": _float(prob_metrics.get("log_loss")),
        "ece_pred_label": _float(prob_metrics.get("ece_pred_label")),
        "event_trades": _float(event_bt.get("trades")),
        "event_hit_rate": _float(event_bt.get("hit_rate")),
        "event_mean_net_pnl_bps": _float(event_bt.get("mean_net_pnl_bps")),
        "event_total_net_pnl_bps": _float(event_bt.get("total_net_pnl_bps")),
        "event_max_drawdown_bps": _float(event_bt.get("max_drawdown_bps")),
        "strict_trades": _float(strict_bt.get("trades")),
        "strict_hit_rate": _float(strict_bt.get("hit_rate")),
        "strict_mean_net_pnl_bps": _float(strict_bt.get("mean_net_pnl_bps")),
        "strict_total_net_pnl_bps": _float(strict_bt.get("total_net_pnl_bps")),
        "strict_max_drawdown_bps": _float(strict_bt.get("max_drawdown_bps")),
    }


def _null_record(fold: int, metrics: dict[str, object], event_bt: dict[str, float]) -> dict[str, object]:
    return {
        "fold": fold,
        "accuracy": _float(metrics.get("accuracy")),
        "balanced_accuracy": _float(metrics.get("balanced_accuracy")),
        "macro_f1": _float(metrics.get("macro_f1")),
        "event_trades": _float(event_bt.get("trades")),
        "event_hit_rate": _float(event_bt.get("hit_rate")),
        "event_mean_net_pnl_bps": _float(event_bt.get("mean_net_pnl_bps")),
        "event_total_net_pnl_bps": _float(event_bt.get("total_net_pnl_bps")),
    }


def _float(value: object) -> float:
    try:
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return 0.0
        return out
    except Exception:
        return 0.0


def _finite_mean(series: pd.Series) -> float:
    arr = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    return float(arr.mean()) if len(arr) else 0.0


def _finite_std(series: pd.Series) -> float:
    arr = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    return float(arr.std(ddof=1)) if len(arr) > 1 else 0.0
