from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from .config import AppConfig
from .data_schema import read_csv
from .execution import backtest_taker_bidask_non_overlapping, robust_profit_gate, sweep_taker_bidask
from .features import build_features
from .kline_features import append_kline_features
from .labels import add_future_labels
from .models import evaluate_classification, evaluate_probabilities, predict_frame, select_feature_columns, train_model
from .pipeline import _label_distribution
from .stress import block_bootstrap_pnl
from .validation import infer_median_step_sec, make_walk_forward_folds, seconds_to_rows


DEFAULT_MODELS = ["logistic", "hgb", "et"]


def run_ensemble_walk_forward(
    *,
    book_path: str | Path,
    trades_path: str | Path | None,
    base_config_path: str | Path | None,
    out_dir: str | Path,
    horizon_sec: float,
    threshold_bps: float,
    model_types: list[str] | None = None,
    candidate_edges: list[float] | None = None,
    cost_bps: float = 1.5,
    latency_sec: float = 0.5,
    stress_cost_bps_values: list[float] | None = None,
    stress_latency_sec_values: list[float] | None = None,
    folds: int = 2,
    min_train_ratio: float = 0.5,
    valid_ratio: float = 0.15,
    calibration_ratio: float = 0.2,
    embargo_sec: float | None = None,
    top_k_features: int = 0,
    min_calibration_trades: int = 10,
    stationary_only: bool = False,
    kline_timeframes: list[str] | None = None,
    kline_candle_paths: dict[str, list[str | Path]] | None = None,
    kline_decision_lag_sec: float = 0.0,
    kline_lookbacks: list[int] | None = None,
    clean: bool = False,
) -> dict[str, object]:
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    cfg = AppConfig.from_yaml(base_config_path)
    cfg.labels.horizon_sec = float(horizon_sec)
    cfg.labels.threshold_bps = float(threshold_bps)
    model_types = [m.strip() for m in (model_types or DEFAULT_MODELS) if m.strip()]
    candidate_edges = candidate_edges or [0.1, 0.2, 0.3, 0.5, 0.7, 0.9]
    stress_cost_bps_values = stress_cost_bps_values or [cost_bps, max(cost_bps * 2.0, cost_bps + 1.5)]
    stress_latency_sec_values = stress_latency_sec_values or [0.0, latency_sec, max(latency_sec * 2.0, latency_sec + 0.5)]

    book = read_csv(book_path)
    trades = read_csv(trades_path) if trades_path else None
    features = build_features(book, trades=trades, cfg=cfg.features, timestamp_col=cfg.io.timestamp_col)
    kline_audit: dict[str, object] | None = None
    if kline_timeframes or kline_candle_paths:
        kline_result = append_kline_features(
            features,
            book=book,
            candle_paths_by_timeframe=kline_candle_paths,
            timeframes=kline_timeframes,
            timestamp_col=cfg.io.timestamp_col,
            decision_lag_sec=float(kline_decision_lag_sec),
            lookbacks=kline_lookbacks,
        )
        features = kline_result.features
        kline_audit = kline_result.audit
        (out / "kline_feature_audit.json").write_text(json.dumps(kline_audit, indent=2), encoding="utf-8")
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
        raise ValueError("no valid ensemble walk-forward folds created")

    all_feature_columns = select_feature_columns(dataset)
    if stationary_only:
        all_feature_columns = filter_stationary_feature_columns(all_feature_columns)
    meta_cols = _prediction_meta_columns(dataset)
    if kline_timeframes or kline_candle_paths:
        kline_meta = [c for c in dataset.columns if c.startswith("kline_")]
        meta_cols = list(dict.fromkeys(meta_cols + kline_meta))
    fold_records: list[dict[str, object]] = []
    all_bt_frames: list[pd.DataFrame] = []
    all_calib_sweeps: list[pd.DataFrame] = []
    feature_records: list[pd.DataFrame] = []

    for fold in fold_defs:
        fold_dir = out / f"fold_{fold.fold:02d}"
        fold_dir.mkdir(exist_ok=True)
        train_df = dataset.iloc[fold.train_start : fold.train_end].copy()
        valid_df = dataset.iloc[fold.valid_start : fold.valid_end].copy()

        calib_rows = max(50, int(len(train_df) * float(calibration_ratio)))
        calib_rows = min(calib_rows, max(50, len(train_df) // 2))
        core_df = train_df.iloc[: len(train_df) - calib_rows].copy()
        calib_df = train_df.iloc[len(train_df) - calib_rows :].copy()
        if len(core_df) < 100:
            core_df = train_df.iloc[: int(len(train_df) * 0.7)].copy()
            calib_df = train_df.iloc[int(len(train_df) * 0.7) :].copy()

        feature_columns = select_stable_feature_columns(core_df, all_feature_columns, top_k=top_k_features)
        pd.Series(feature_columns).to_csv(fold_dir / "selected_features.csv", index=False, header=["feature"])
        feature_records.append(pd.DataFrame({"fold": fold.fold, "feature": feature_columns}))

        calib_pred = _fit_predict_ensemble(core_df, calib_df, feature_columns, meta_cols, cfg, model_types)
        calib_sweep = sweep_taker_bidask(
            calib_pred,
            horizon_sec=cfg.labels.horizon_sec,
            cost_bps_values=[float(cost_bps)],
            latency_sec_values=[float(latency_sec)],
            edge_thresholds=candidate_edges,
        )
        feasible = calib_sweep[calib_sweep["trades"].astype(float) >= float(min_calibration_trades)].copy()
        chosen = feasible.head(1) if not feasible.empty else calib_sweep.head(1)
        selected_edge = float(chosen.iloc[0]["edge_threshold"]) if not chosen.empty else float(candidate_edges[0])

        valid_pred = _fit_predict_ensemble(train_df, valid_df, feature_columns, meta_cols, cfg, model_types)
        valid_pred.insert(0, "fold", fold.fold)
        valid_pred["selected_edge_threshold"] = selected_edge
        bt_frame, bt = backtest_taker_bidask_non_overlapping(
            valid_pred,
            cost_bps=float(cost_bps),
            edge_threshold=selected_edge,
            horizon_sec=cfg.labels.horizon_sec,
            latency_sec=float(latency_sec),
        )
        bt_frame.to_csv(fold_dir / "validation_taker_backtest.csv", index=False)
        valid_pred.to_csv(fold_dir / "validation_predictions.csv", index=False)
        calib_pred.to_csv(fold_dir / "calibration_predictions.csv", index=False)
        calib_sweep.to_csv(fold_dir / "calibration_taker_sweep.csv", index=False)
        all_bt_frames.append(bt_frame)
        all_calib_sweeps.append(calib_sweep.assign(fold=fold.fold))

        metrics = evaluate_classification(valid_df["label"], valid_pred["pred_label"])
        prob_metrics = evaluate_probabilities(valid_df["label"], valid_pred)
        boot = block_bootstrap_pnl(bt_frame.loc[bt_frame["traded"] == 1, "net_pnl_bps"], iterations=500, block_size=10, seed=cfg.model.random_state + fold.fold)
        selected_row = chosen.to_dict(orient="records")[0] if not chosen.empty else {}
        fold_records.append(
            {
                "fold": fold.fold,
                "train_rows": int(len(train_df)),
                "core_rows": int(len(core_df)),
                "calibration_rows": int(len(calib_df)),
                "valid_rows": int(len(valid_df)),
                "feature_count": int(len(feature_columns)),
                "selected_edge_threshold": selected_edge,
                "calib_trades": _float(selected_row.get("trades")),
                "calib_mean_net_pnl_bps": _float(selected_row.get("mean_net_pnl_bps")),
                "calib_total_net_pnl_bps": _float(selected_row.get("total_net_pnl_bps")),
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
        )

    folds_df = pd.DataFrame(fold_records)
    folds_df.to_csv(out / "fold_metrics.csv", index=False)
    oof = pd.concat(all_bt_frames, ignore_index=True) if all_bt_frames else pd.DataFrame()
    oof.to_csv(out / "oof_taker_backtest.csv", index=False)
    calibs = pd.concat(all_calib_sweeps, ignore_index=True) if all_calib_sweeps else pd.DataFrame()
    calibs.to_csv(out / "calibration_taker_sweeps.csv", index=False)
    selected_features = pd.concat(feature_records, ignore_index=True) if feature_records else pd.DataFrame()
    selected_features.to_csv(out / "selected_features_by_fold.csv", index=False)

    stress = sweep_taker_bidask(
        oof,
        horizon_sec=cfg.labels.horizon_sec,
        cost_bps_values=stress_cost_bps_values,
        latency_sec_values=stress_latency_sec_values,
        edge_thresholds=candidate_edges,
    ) if not oof.empty else pd.DataFrame()
    stress.to_csv(out / "oof_taker_stress_sweep.csv", index=False)
    gate = robust_profit_gate(stress, min_trades=max(1, int(min_calibration_trades))) if not stress.empty else {"passed": False, "reason": "no oof"}

    aggregate = _aggregate_v05(folds_df, oof, stress, gate)
    result = {
        "book_path": str(book_path),
        "trades_path": str(trades_path) if trades_path else None,
        "rows_features": int(len(features)),
        "rows_dataset": int(len(dataset)),
        "feature_count_all": int(len(all_feature_columns)),
        "median_step_sec": infer_median_step_sec(dataset["timestamp"]),
        "horizon_sec": float(horizon_sec),
        "threshold_bps": float(threshold_bps),
        "models": model_types,
        "candidate_edges": [float(x) for x in candidate_edges],
        "cost_bps": float(cost_bps),
        "latency_sec": float(latency_sec),
        "stress_cost_bps_values": [float(x) for x in stress_cost_bps_values],
        "stress_latency_sec_values": [float(x) for x in stress_latency_sec_values],
        "top_k_features": int(top_k_features),
        "stationary_only": bool(stationary_only),
        "kline_timeframes": [str(x) for x in (kline_timeframes or [])],
        "kline_candle_paths": {str(k): [str(vv) for vv in v] for k, v in (kline_candle_paths or {}).items()},
        "kline_decision_lag_sec": float(kline_decision_lag_sec),
        "kline_lookbacks": [int(x) for x in (kline_lookbacks or [])],
        "kline_audit": kline_audit,
        "folds": [fold.__dict__ for fold in fold_defs],
        "aggregate": aggregate,
        "profit_gate": gate,
        "out_dir": str(out),
    }
    cfg.to_yaml(out / "config_resolved.yaml")
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_ensemble_report(out / "REPORT.md", result, folds_df, stress)
    return result


def _fit_predict_ensemble(
    train_df: pd.DataFrame,
    target_df: pd.DataFrame,
    feature_columns: list[str],
    meta_cols: list[str],
    cfg: AppConfig,
    model_types: list[str],
) -> pd.DataFrame:
    preds: list[pd.DataFrame] = []
    base_type = cfg.model.type
    for model_type in model_types:
        cfg.model.type = model_type
        model = train_model(train_df[feature_columns], train_df["label"], cfg.model)
        pred = predict_frame(model, target_df[feature_columns], target_df[meta_cols])
        pred["model_type"] = model_type
        preds.append(pred)
    cfg.model.type = base_type
    return average_prediction_frames(preds)


def average_prediction_frames(preds: list[pd.DataFrame]) -> pd.DataFrame:
    if not preds:
        raise ValueError("no prediction frames to average")
    out = preds[0].drop(columns=["model_type"], errors="ignore").copy().reset_index(drop=True)
    for col in ["prob_down", "prob_flat", "prob_up"]:
        arr = np.vstack([p[col].astype(float).to_numpy() for p in preds])
        out[col] = arr.mean(axis=0)
    labels = np.array([-1, 0, 1])
    probs = out[["prob_down", "prob_flat", "prob_up"]].to_numpy(dtype=float)
    out["pred_label"] = labels[np.argmax(probs, axis=1)].astype(int)
    out["prob_edge"] = out["prob_up"].astype(float) - out["prob_down"].astype(float)
    out["prob_confidence"] = out[["prob_down", "prob_flat", "prob_up"]].max(axis=1)
    out["ensemble_size"] = len(preds)
    return out


def select_stable_feature_columns(frame: pd.DataFrame, feature_columns: list[str], top_k: int = 0) -> list[str]:
    if top_k <= 0 or top_k >= len(feature_columns):
        return list(feature_columns)
    y = frame["future_return_bps"].astype(float)
    rows: list[tuple[str, float]] = []
    for col in feature_columns:
        x = pd.to_numeric(frame[col], errors="coerce")
        if x.nunique(dropna=True) <= 1:
            score = 0.0
        else:
            score = abs(float(x.corr(y, method="spearman")))
            if not np.isfinite(score):
                score = 0.0
        rows.append((col, score))
    ranked = [name for name, _ in sorted(rows, key=lambda item: item[1], reverse=True)]
    must_keep = [c for c in ["spread_bps", "microprice_dev_bps", "imbalance_l1", "imbalance_l3", "imbalance_l5", "imbalance_l10"] if c in feature_columns]
    selected: list[str] = []
    for col in must_keep + ranked:
        if col not in selected:
            selected.append(col)
        if len(selected) >= top_k:
            break
    return selected


def filter_stationary_feature_columns(feature_columns: list[str]) -> list[str]:
    """Drop absolute price-level features that can memorize a single session.

    Keep distances, bps-normalized values, imbalances, returns, volatility, OFI, and
    depth features. Drop raw mid/bid/ask/microprice levels and their rolling means.
    """
    exact = {
        "mid",
        "best_bid",
        "best_ask",
        "weighted_mid_l1",
        "microprice_l1",
        "spread",
    }
    out: list[str] = []
    for col in feature_columns:
        if col in exact:
            continue
        if col.startswith("microprice_l") and "dev_bps" not in col:
            continue
        if col.startswith("weighted_mid_l") and "dev_bps" not in col:
            continue
        # Rolling transforms of absolute price features inherit the same leakage risk.
        if col.startswith(("mid_", "best_bid_", "best_ask_", "microprice_l", "weighted_mid_l")) and "dev_bps" not in col:
            if "ret" not in col and "vol" not in col:
                continue
        out.append(col)
    return out


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


def _aggregate_v05(folds_df: pd.DataFrame, oof: pd.DataFrame, stress: pd.DataFrame, gate: dict[str, object]) -> dict[str, object]:
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
    if not stress.empty:
        out["best_stress_row"] = stress.head(1).to_dict(orient="records")[0]
    out["robust_profit_gate_passed"] = bool(gate.get("passed"))
    out["strict_research_pass"] = bool(
        out.get("valid_mean_net_pnl_bps_min", -999.0) > 0.0
        and out.get("bootstrap_mean_p05_bps_min", -999.0) > 0.0
        and out.get("valid_trades_min", 0.0) >= 20.0
        and gate.get("passed") is True
    )
    return out


def write_ensemble_report(path: str | Path, result: dict[str, object], folds_df: pd.DataFrame, stress: pd.DataFrame) -> None:
    aggregate = result.get("aggregate", {}) if isinstance(result.get("aggregate"), dict) else {}
    gate = result.get("profit_gate", {}) if isinstance(result.get("profit_gate"), dict) else {}
    lines = [
        "# V05 Ensemble Walk-forward Report",
        "",
        f"Book path: `{result.get('book_path')}`",
        f"Rows after labels: {result.get('rows_dataset')}",
        f"Models: `{', '.join(result.get('models', []))}`",
        f"Horizon seconds: {result.get('horizon_sec')}",
        f"Primary cost bps: {result.get('cost_bps')}",
        f"Primary latency seconds: {result.get('latency_sec')}",
        f"Top-k feature selection: {result.get('top_k_features')}",
        f"K-line timeframes: `{', '.join(result.get('kline_timeframes', []) or [])}`",
        f"K-line feature count: `{(result.get('kline_audit') or {}).get('feature_count') if isinstance(result.get('kline_audit'), dict) else 0}`",
        "",
        "## Fold metrics",
        "",
    ]
    display_cols = [
        "fold",
        "feature_count",
        "selected_edge_threshold",
        "valid_trades",
        "valid_hit_rate",
        "valid_mean_net_pnl_bps",
        "valid_total_net_pnl_bps",
        "bootstrap_mean_p05_bps",
        "balanced_accuracy",
    ]
    existing = [c for c in display_cols if c in folds_df.columns]
    lines.append(folds_df[existing].to_markdown(index=False) if not folds_df.empty else "No folds.")
    lines.extend(["", "## Aggregate", "", "```json", json.dumps(aggregate, indent=2), "```", ""])
    lines.extend(["## Robust profit gate", "", "```json", json.dumps(gate, indent=2), "```", ""])
    if not stress.empty:
        cols = ["cost_bps", "latency_sec", "edge_threshold", "trades", "hit_rate", "mean_net_pnl_bps", "total_net_pnl_bps", "max_drawdown_bps"]
        lines.extend(["## OOF taker bid/ask stress sweep", "", stress[cols].head(20).to_markdown(index=False), ""])
    lines.extend(
        [
            "## Interpretation",
            "",
            "This report uses calibration-only edge selection and taker bid/ask execution. A pass requires positive fold minimums, positive bootstrap lower bounds, and a robust stress gate. Treat failures as useful evidence against deployment, not as implementation failure.",
            "",
        ]
    )
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def _float(value: object) -> float:
    try:
        f = float(value)
        return f if np.isfinite(f) else 0.0
    except Exception:
        return 0.0


def _finite_mean(series: pd.Series) -> float:
    arr = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    return float(arr.mean()) if len(arr) else 0.0


def _finite_min(series: pd.Series) -> float:
    arr = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    return float(arr.min()) if len(arr) else 0.0
