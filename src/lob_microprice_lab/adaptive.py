from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from .config import AppConfig
from .data_schema import read_csv
from .features import build_features
from .labels import add_future_labels
from .models import evaluate_classification, evaluate_probabilities, predict_frame, select_feature_columns, train_model
from .pipeline import _label_distribution
from .stress import backtest_latency_non_overlapping, stress_sweep_predictions, block_bootstrap_pnl
from .validation import infer_median_step_sec, make_walk_forward_folds, seconds_to_rows


def run_adaptive_walk_forward(
    *,
    book_path: str | Path,
    trades_path: str | Path | None,
    base_config_path: str | Path | None,
    out_dir: str | Path,
    horizon_sec: float,
    threshold_bps: float,
    model_type: str,
    candidate_edges: list[float],
    cost_bps: float,
    latency_sec: float,
    folds: int = 3,
    min_train_ratio: float = 0.50,
    valid_ratio: float = 0.15,
    calibration_ratio: float = 0.20,
    embargo_sec: float | None = None,
    min_calibration_trades: int = 5,
    clean: bool = False,
) -> dict[str, object]:
    """Walk-forward with edge threshold selected only from a past calibration window.

    This prevents the common research error of selecting the probability threshold from the same OOF validation results that
    are later reported as performance.
    """
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    cfg = AppConfig.from_yaml(base_config_path)
    cfg.labels.horizon_sec = float(horizon_sec)
    cfg.labels.threshold_bps = float(threshold_bps)
    cfg.model.type = str(model_type)
    cfg.backtest.cost_bps = float(cost_bps)

    book = read_csv(book_path)
    trades = read_csv(trades_path) if trades_path else None
    features = build_features(book, trades=trades, cfg=cfg.features, timestamp_col=cfg.io.timestamp_col)
    dataset = add_future_labels(features, horizon_sec=cfg.labels.horizon_sec, threshold_bps=cfg.labels.threshold_bps)
    if len(dataset) < 500:
        raise ValueError(f"adaptive walk-forward needs at least 500 labeled rows, got {len(dataset)}")

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
        raise ValueError("no valid adaptive walk-forward folds created")

    feature_columns = select_feature_columns(dataset)
    meta_cols = _prediction_meta_columns(dataset)
    fold_rows: list[dict[str, object]] = []
    all_predictions: list[pd.DataFrame] = []
    calibration_rows: list[pd.DataFrame] = []

    for fold in fold_defs:
        fold_dir = out / f"fold_{fold.fold:02d}"
        fold_dir.mkdir(exist_ok=True)
        train_df = dataset.iloc[fold.train_start : fold.train_end].copy()
        valid_df = dataset.iloc[fold.valid_start : fold.valid_end].copy()
        if len(train_df) < 200 or len(valid_df) < 50:
            continue

        calib_rows = max(50, int(len(train_df) * float(calibration_ratio)))
        calib_rows = min(calib_rows, max(50, len(train_df) // 2))
        core_df = train_df.iloc[: len(train_df) - calib_rows].copy()
        calib_df = train_df.iloc[len(train_df) - calib_rows :].copy()
        if len(core_df) < 100 or len(calib_df) < 50:
            core_df = train_df.iloc[: int(len(train_df) * 0.7)].copy()
            calib_df = train_df.iloc[int(len(train_df) * 0.7) :].copy()

        core_model = train_model(core_df[feature_columns], core_df["label"], cfg.model)
        calib_pred = predict_frame(core_model, calib_df[feature_columns], calib_df[meta_cols])
        calib_sweep = stress_sweep_predictions(
            calib_pred,
            horizon_sec=cfg.labels.horizon_sec,
            cost_bps_values=[float(cost_bps)],
            latency_sec_values=[float(latency_sec)],
            edge_thresholds=candidate_edges,
        )
        feasible = calib_sweep[calib_sweep["trades"] >= float(min_calibration_trades)].copy()
        chosen = feasible.head(1) if not feasible.empty else calib_sweep.head(1)
        if chosen.empty:
            selected_edge = float(candidate_edges[0])
            selected_row: dict[str, object] = {}
        else:
            selected_row = chosen.to_dict(orient="records")[0]
            selected_edge = float(selected_row.get("edge_threshold", candidate_edges[0]))

        final_model = train_model(train_df[feature_columns], train_df["label"], cfg.model)
        pred = predict_frame(final_model, valid_df[feature_columns], valid_df[meta_cols])
        pred.insert(0, "fold", fold.fold)
        pred["selected_edge_threshold"] = selected_edge
        metrics = evaluate_classification(valid_df["label"], pred["pred_label"])
        prob_metrics = evaluate_probabilities(valid_df["label"], pred)
        bt_frame, bt = backtest_latency_non_overlapping(
            pred,
            cost_bps=float(cost_bps),
            edge_threshold=selected_edge,
            horizon_sec=cfg.labels.horizon_sec,
            latency_sec=float(latency_sec),
        )
        trades_only = bt_frame[bt_frame["traded"] == 1]
        boot = block_bootstrap_pnl(trades_only["net_pnl_bps"], iterations=500, block_size=10, seed=cfg.model.random_state + fold.fold)

        calib_pred.to_csv(fold_dir / "calibration_predictions.csv", index=False)
        calib_sweep.to_csv(fold_dir / "calibration_edge_sweep.csv", index=False)
        bt_frame.to_csv(fold_dir / "validation_backtest.csv", index=False)
        pred.to_csv(fold_dir / "validation_predictions.csv", index=False)
        all_predictions.append(bt_frame)
        calibration_rows.append(calib_sweep.assign(fold=fold.fold))

        row = {
            "fold": fold.fold,
            "train_rows": int(len(train_df)),
            "core_rows": int(len(core_df)),
            "calibration_rows": int(len(calib_df)),
            "valid_rows": int(len(valid_df)),
            "selected_edge_threshold": selected_edge,
            "calib_mean_net_pnl_bps": _float(selected_row.get("mean_net_pnl_bps")) if selected_row else 0.0,
            "calib_total_net_pnl_bps": _float(selected_row.get("total_net_pnl_bps")) if selected_row else 0.0,
            "calib_trades": _float(selected_row.get("trades")) if selected_row else 0.0,
            "accuracy": _float(metrics.get("accuracy")),
            "balanced_accuracy": _float(metrics.get("balanced_accuracy")),
            "macro_f1": _float(metrics.get("macro_f1")),
            "log_loss": _float(prob_metrics.get("log_loss")),
            "ece_pred_label": _float(prob_metrics.get("ece_pred_label")),
            "valid_trades": _float(bt.get("trades")),
            "valid_hit_rate": _float(bt.get("hit_rate")),
            "valid_mean_net_pnl_bps": _float(bt.get("mean_net_pnl_bps")),
            "valid_total_net_pnl_bps": _float(bt.get("total_net_pnl_bps")),
            "valid_max_drawdown_bps": _float(bt.get("max_drawdown_bps")),
            "bootstrap_mean_p05_bps": _float(boot.get("mean_p05_bps")),
            "bootstrap_prob_mean_gt_0": _float(boot.get("prob_mean_gt_0")),
            "label_distribution_train": json.dumps(_label_distribution(train_df["label"]), sort_keys=True),
            "label_distribution_valid": json.dumps(_label_distribution(valid_df["label"]), sort_keys=True),
        }
        fold_rows.append(row)

    folds_df = pd.DataFrame(fold_rows)
    folds_df.to_csv(out / "fold_metrics.csv", index=False)
    oof = pd.concat(all_predictions, ignore_index=True) if all_predictions else pd.DataFrame()
    oof.to_csv(out / "oof_adaptive_backtest.csv", index=False)
    calibs = pd.concat(calibration_rows, ignore_index=True) if calibration_rows else pd.DataFrame()
    calibs.to_csv(out / "calibration_edge_sweeps.csv", index=False)
    aggregate = _aggregate(folds_df, oof)
    result = {
        "book_path": str(book_path),
        "trades_path": str(trades_path) if trades_path else None,
        "rows_features": int(len(features)),
        "rows_dataset": int(len(dataset)),
        "feature_count": int(len(feature_columns)),
        "median_step_sec": infer_median_step_sec(dataset["timestamp"]),
        "horizon_sec": float(horizon_sec),
        "threshold_bps": float(threshold_bps),
        "cost_bps": float(cost_bps),
        "latency_sec": float(latency_sec),
        "candidate_edges": [float(x) for x in candidate_edges],
        "folds": [fold.__dict__ for fold in fold_defs],
        "aggregate": aggregate,
        "out_dir": str(out),
    }
    cfg.to_yaml(out / "config_resolved.yaml")
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_adaptive_report(out / "REPORT.md", result, folds_df)
    return result


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


def _aggregate(folds_df: pd.DataFrame, oof: pd.DataFrame) -> dict[str, object]:
    out: dict[str, object] = {}
    for col in [
        "accuracy",
        "balanced_accuracy",
        "macro_f1",
        "valid_trades",
        "valid_hit_rate",
        "valid_mean_net_pnl_bps",
        "valid_total_net_pnl_bps",
        "valid_max_drawdown_bps",
        "bootstrap_mean_p05_bps",
        "bootstrap_prob_mean_gt_0",
    ]:
        if col in folds_df.columns:
            out[f"{col}_mean"] = _finite_mean(folds_df[col])
            out[f"{col}_min"] = _finite_min(folds_df[col])
    if not oof.empty and "net_pnl_bps" in oof.columns:
        trades = oof[oof["traded"] == 1]
        out["oof_trades"] = int(len(trades))
        out["oof_total_net_pnl_bps"] = float(trades["net_pnl_bps"].sum()) if len(trades) else 0.0
        out["oof_mean_net_pnl_bps"] = float(trades["net_pnl_bps"].mean()) if len(trades) else 0.0
        out["oof_hit_rate"] = float((trades["net_pnl_bps"] > 0).mean()) if len(trades) else 0.0
    out["strict_research_pass"] = bool(
        out.get("valid_mean_net_pnl_bps_min", -999.0) > 0.0
        and out.get("bootstrap_mean_p05_bps_min", -999.0) > 0.0
        and out.get("valid_trades_min", 0.0) >= 20.0
    )
    return out


def write_adaptive_report(path: str | Path, result: dict[str, object], folds_df: pd.DataFrame) -> None:
    aggregate = result.get("aggregate", {}) if isinstance(result.get("aggregate"), dict) else {}
    lines = [
        "# V04 Adaptive Walk-forward Report",
        "",
        f"Book path: `{result.get('book_path')}`",
        f"Rows after labels: {result.get('rows_dataset')}",
        f"Feature count: {result.get('feature_count')}",
        f"Horizon seconds: {result.get('horizon_sec')}",
        f"Cost bps: {result.get('cost_bps')}",
        f"Latency seconds: {result.get('latency_sec')}",
        "",
        "## Fold metrics",
        "",
    ]
    cols = [
        "fold",
        "selected_edge_threshold",
        "calib_trades",
        "calib_mean_net_pnl_bps",
        "valid_trades",
        "valid_hit_rate",
        "valid_mean_net_pnl_bps",
        "valid_total_net_pnl_bps",
        "valid_max_drawdown_bps",
        "bootstrap_mean_p05_bps",
        "bootstrap_prob_mean_gt_0",
        "balanced_accuracy",
    ]
    existing = [c for c in cols if c in folds_df.columns]
    lines.append(folds_df[existing].to_markdown(index=False) if not folds_df.empty else "No completed folds.")
    lines.extend(["", "## Aggregate", "", "```json", json.dumps(aggregate, indent=2), "```", ""])
    lines.extend(
        [
            "## Notes",
            "",
            "Each fold selects the edge threshold on a past calibration window, then evaluates that fixed threshold on the future validation window with latency-aware non-overlap accounting.",
            "",
        ]
    )
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def _float(value: object) -> float:
    try:
        x = float(value)
        if np.isnan(x) or np.isinf(x):
            return 0.0
        return x
    except Exception:
        return 0.0


def _finite_mean(series: pd.Series) -> float:
    arr = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    return float(arr.mean()) if len(arr) else 0.0


def _finite_min(series: pd.Series) -> float:
    arr = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    return float(arr.min()) if len(arr) else 0.0
