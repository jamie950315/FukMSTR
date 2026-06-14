from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .backtest import backtest_predictions, backtest_predictions_non_overlapping, save_backtest_report, sweep_edge_thresholds
from .config import AppConfig
from .data_schema import read_csv
from .features import build_features
from .labels import add_future_labels
from .models import (
    evaluate_classification,
    evaluate_probabilities,
    feature_importance_frame,
    predict_frame,
    save_model_artifacts,
    select_feature_columns,
    train_model,
)


def prepare_dataset(book_path: str | Path, trades_path: str | Path | None, cfg: AppConfig) -> pd.DataFrame:
    book = read_csv(book_path)
    trades = read_csv(trades_path) if trades_path else None
    features = build_features(book, trades=trades, cfg=cfg.features, timestamp_col=cfg.io.timestamp_col)
    dataset = add_future_labels(features, horizon_sec=cfg.labels.horizon_sec, threshold_bps=cfg.labels.threshold_bps)
    return dataset


def chronological_split(frame: pd.DataFrame, train_ratio: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not 0.1 <= train_ratio <= 0.95:
        raise ValueError("train_ratio must be between 0.1 and 0.95")
    split_idx = int(len(frame) * train_ratio)
    if split_idx <= 0 or split_idx >= len(frame):
        raise ValueError("not enough rows for chronological split")
    return frame.iloc[:split_idx].copy(), frame.iloc[split_idx:].copy()


def run_train(book_path: str | Path, trades_path: str | Path | None, config_path: str | Path | None, out_dir: str | Path) -> dict[str, object]:
    cfg = AppConfig.from_yaml(config_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    dataset = prepare_dataset(book_path, trades_path, cfg)
    if len(dataset) < 100:
        raise ValueError(f"dataset too small after feature/label construction: {len(dataset)} rows")

    train_df, valid_df = chronological_split(dataset, cfg.split.train_ratio)
    feature_columns = select_feature_columns(dataset)
    X_train = train_df[feature_columns]
    y_train = train_df["label"]
    X_valid = valid_df[feature_columns]
    y_valid = valid_df["label"]

    model = train_model(X_train, y_train, cfg.model)
    meta_cols = _prediction_meta_columns(valid_df)
    pred_valid = predict_frame(model, X_valid, valid_df[meta_cols])

    metrics = evaluate_classification(y_valid, pred_valid["pred_label"])
    prob_metrics = evaluate_probabilities(y_valid, pred_valid)
    bt_frame, bt_metrics = backtest_predictions(
        pred_valid,
        cost_bps=cfg.backtest.cost_bps,
        edge_threshold=cfg.backtest.signal_edge_threshold,
    )
    strict_frame, strict_bt_metrics = backtest_predictions_non_overlapping(
        pred_valid,
        cost_bps=cfg.backtest.cost_bps,
        edge_threshold=cfg.backtest.signal_edge_threshold,
        horizon_sec=cfg.labels.horizon_sec,
    )
    edge_sweep = sweep_edge_thresholds(
        pred_valid,
        cost_bps=cfg.backtest.cost_bps,
        thresholds=[0.05, 0.10, 0.20, 0.30, 0.50, 0.70, 0.90],
        horizon_sec=cfg.labels.horizon_sec,
    )
    importances = feature_importance_frame(model, feature_columns, top_n=50)

    save_model_artifacts(model, feature_columns, out)
    cfg.to_yaml(out / "config_resolved.yaml")
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (out / "probability_metrics.json").write_text(json.dumps(prob_metrics, indent=2), encoding="utf-8")
    save_backtest_report(bt_metrics, out / "backtest.json")
    save_backtest_report(strict_bt_metrics, out / "backtest_non_overlap.json")
    pred_valid.to_csv(out / "predictions_valid.csv", index=False)
    bt_frame.to_csv(out / "backtest_valid.csv", index=False)
    strict_frame.to_csv(out / "backtest_valid_non_overlap.csv", index=False)
    edge_sweep.to_csv(out / "edge_sweep.csv", index=False)
    importances.to_csv(out / "feature_importance.csv", index=False)

    summary = {
        "rows_total": int(len(dataset)),
        "rows_train": int(len(train_df)),
        "rows_valid": int(len(valid_df)),
        "feature_count": int(len(feature_columns)),
        "label_distribution_train": _label_distribution(y_train),
        "label_distribution_valid": _label_distribution(y_valid),
        "metrics": metrics,
        "probability_metrics": prob_metrics,
        "backtest": bt_metrics,
        "backtest_non_overlap": strict_bt_metrics,
        "best_edge_sweep": edge_sweep.head(10).to_dict(orient="records") if not edge_sweep.empty else [],
        "out_dir": str(out),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary



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
    ]
    return [c for c in base + candidates if c in frame.columns]

def _label_distribution(labels: pd.Series) -> dict[str, int]:
    return {str(int(k)): int(v) for k, v in labels.value_counts().sort_index().items()}
