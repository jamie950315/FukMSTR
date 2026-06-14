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
from .labels import add_future_labels
from .stress import block_bootstrap_pnl
from .validation import infer_median_step_sec, make_walk_forward_folds, seconds_to_rows

DEFAULT_RULE_FEATURES = [
    "imbalance_l1",
    "imbalance_l3",
    "imbalance_l5",
    "imbalance_l10",
    "microprice_dev_bps",
    "microprice_dev_bps_l3",
    "microprice_dev_bps_l5",
    "microprice_dev_bps_l10",
    "weighted_mid_dev_bps",
    "mid_ret_2r_bps",
    "mid_ret_5r_bps",
    "mid_ret_10r_bps",
    "mid_ret_20r_bps",
]


def run_rule_taker_walk_forward(
    *,
    book_path: str | Path,
    trades_path: str | Path | None,
    base_config_path: str | Path | None,
    out_dir: str | Path,
    horizon_sec: float,
    threshold_bps: float,
    rule_features: list[str] | None = None,
    signal_thresholds: list[float] | None = None,
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
    min_calibration_trades: int = 10,
    clean: bool = False,
) -> dict[str, object]:
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    cfg = AppConfig.from_yaml(base_config_path)
    cfg.labels.horizon_sec = float(horizon_sec)
    cfg.labels.threshold_bps = float(threshold_bps)
    signal_thresholds = signal_thresholds or [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7]
    candidate_edges = candidate_edges or [0.5]
    stress_cost_bps_values = stress_cost_bps_values or [cost_bps, max(cost_bps * 2.0, cost_bps + 1.5)]
    stress_latency_sec_values = stress_latency_sec_values or [0.0, latency_sec, max(latency_sec * 2.0, latency_sec + 0.5)]

    book = read_csv(book_path)
    trades = read_csv(trades_path) if trades_path else None
    features = build_features(book, trades=trades, cfg=cfg.features, timestamp_col=cfg.io.timestamp_col)
    dataset = add_future_labels(features, horizon_sec=cfg.labels.horizon_sec, threshold_bps=cfg.labels.threshold_bps)
    available_rules = [c for c in (rule_features or DEFAULT_RULE_FEATURES) if c in dataset.columns]
    if not available_rules:
        raise ValueError("no requested rule feature is available in dataset")

    embargo = cfg.labels.horizon_sec if embargo_sec is None else float(embargo_sec)
    embargo_rows = seconds_to_rows(dataset["timestamp"], embargo)
    fold_defs = make_walk_forward_folds(
        len(dataset),
        folds=int(folds),
        min_train_ratio=float(min_train_ratio),
        valid_ratio=float(valid_ratio),
        embargo_rows=embargo_rows,
    )
    meta_cols = [c for c in ["timestamp", "best_bid", "best_ask", "mid", "future_best_bid", "future_best_ask", "future_mid", "future_return_bps", "label"] + available_rules if c in dataset.columns]

    fold_records: list[dict[str, object]] = []
    all_bt: list[pd.DataFrame] = []
    all_calib: list[pd.DataFrame] = []

    for fold in fold_defs:
        fold_dir = out / f"fold_{fold.fold:02d}"
        fold_dir.mkdir(exist_ok=True)
        train_df = dataset.iloc[fold.train_start : fold.train_end].copy()
        valid_df = dataset.iloc[fold.valid_start : fold.valid_end].copy()
        calib_rows = max(50, int(len(train_df) * float(calibration_ratio)))
        calib_rows = min(calib_rows, max(50, len(train_df) // 2))
        calib_df = train_df.iloc[len(train_df) - calib_rows :].copy()

        calib_sweeps: list[pd.DataFrame] = []
        for feature in available_rules:
            for threshold in signal_thresholds:
                pred = make_rule_predictions(calib_df, meta_cols, feature, float(threshold))
                sweep = sweep_taker_bidask(
                    pred,
                    horizon_sec=cfg.labels.horizon_sec,
                    cost_bps_values=[float(cost_bps)],
                    latency_sec_values=[float(latency_sec)],
                    edge_thresholds=candidate_edges,
                )
                if not sweep.empty:
                    sweep.insert(0, "rule_feature", feature)
                    sweep.insert(1, "signal_threshold", float(threshold))
                    calib_sweeps.append(sweep)
        calib_table = pd.concat(calib_sweeps, ignore_index=True) if calib_sweeps else pd.DataFrame()
        feasible = calib_table[calib_table["trades"].astype(float) >= float(min_calibration_trades)].copy() if not calib_table.empty else pd.DataFrame()
        chosen = feasible.head(1) if not feasible.empty else calib_table.head(1)
        if chosen.empty:
            selected_feature = available_rules[0]
            selected_threshold = float(signal_thresholds[0])
            selected_edge = float(candidate_edges[0])
            chosen_row: dict[str, object] = {}
        else:
            chosen_row = chosen.to_dict(orient="records")[0]
            selected_feature = str(chosen_row["rule_feature"])
            selected_threshold = float(chosen_row["signal_threshold"])
            selected_edge = float(chosen_row["edge_threshold"])

        valid_pred = make_rule_predictions(valid_df, meta_cols, selected_feature, selected_threshold)
        valid_pred.insert(0, "fold", fold.fold)
        valid_pred["selected_rule_feature"] = selected_feature
        valid_pred["selected_signal_threshold"] = selected_threshold
        valid_pred["selected_edge_threshold"] = selected_edge
        bt_frame, bt = backtest_taker_bidask_non_overlapping(
            valid_pred,
            cost_bps=float(cost_bps),
            edge_threshold=selected_edge,
            horizon_sec=cfg.labels.horizon_sec,
            latency_sec=float(latency_sec),
        )
        boot = block_bootstrap_pnl(bt_frame.loc[bt_frame["traded"] == 1, "net_pnl_bps"], iterations=500, block_size=10, seed=cfg.model.random_state + fold.fold)
        valid_pred.to_csv(fold_dir / "validation_rule_predictions.csv", index=False)
        bt_frame.to_csv(fold_dir / "validation_rule_taker_backtest.csv", index=False)
        calib_table.to_csv(fold_dir / "calibration_rule_taker_sweep.csv", index=False)
        all_bt.append(bt_frame)
        all_calib.append(calib_table.assign(fold=fold.fold))
        fold_records.append(
            {
                "fold": fold.fold,
                "train_rows": int(len(train_df)),
                "calibration_rows": int(len(calib_df)),
                "valid_rows": int(len(valid_df)),
                "selected_rule_feature": selected_feature,
                "selected_signal_threshold": selected_threshold,
                "selected_edge_threshold": selected_edge,
                "calib_trades": _float(chosen_row.get("trades")),
                "calib_mean_net_pnl_bps": _float(chosen_row.get("mean_net_pnl_bps")),
                "calib_total_net_pnl_bps": _float(chosen_row.get("total_net_pnl_bps")),
                "valid_trades": _float(bt.get("trades")),
                "valid_hit_rate": _float(bt.get("hit_rate")),
                "valid_mean_net_pnl_bps": _float(bt.get("mean_net_pnl_bps")),
                "valid_total_net_pnl_bps": _float(bt.get("total_net_pnl_bps")),
                "valid_max_drawdown_bps": _float(bt.get("max_drawdown_bps")),
                "bootstrap_mean_p05_bps": _float(boot.get("mean_p05_bps")),
                "bootstrap_prob_mean_gt_0": _float(boot.get("prob_mean_gt_0")),
            }
        )

    folds_df = pd.DataFrame(fold_records)
    folds_df.to_csv(out / "fold_metrics.csv", index=False)
    oof = pd.concat(all_bt, ignore_index=True) if all_bt else pd.DataFrame()
    oof.to_csv(out / "oof_rule_taker_backtest.csv", index=False)
    calib = pd.concat(all_calib, ignore_index=True) if all_calib else pd.DataFrame()
    calib.to_csv(out / "calibration_rule_taker_sweeps.csv", index=False)
    stress = sweep_taker_bidask(
        oof,
        horizon_sec=cfg.labels.horizon_sec,
        cost_bps_values=stress_cost_bps_values,
        latency_sec_values=stress_latency_sec_values,
        edge_thresholds=candidate_edges,
    ) if not oof.empty else pd.DataFrame()
    stress.to_csv(out / "oof_rule_taker_stress_sweep.csv", index=False)
    gate = robust_profit_gate(stress, min_trades=max(1, int(min_calibration_trades))) if not stress.empty else {"passed": False, "reason": "no oof"}
    aggregate = _aggregate(folds_df, oof, stress, gate)
    result = {
        "book_path": str(book_path),
        "rows_dataset": int(len(dataset)),
        "median_step_sec": infer_median_step_sec(dataset["timestamp"]),
        "horizon_sec": float(horizon_sec),
        "threshold_bps": float(threshold_bps),
        "available_rules": available_rules,
        "signal_thresholds": [float(x) for x in signal_thresholds],
        "candidate_edges": [float(x) for x in candidate_edges],
        "cost_bps": float(cost_bps),
        "latency_sec": float(latency_sec),
        "aggregate": aggregate,
        "profit_gate": gate,
        "out_dir": str(out),
    }
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_rule_taker_report(out / "REPORT.md", result, folds_df, stress)
    return result


def make_rule_predictions(frame: pd.DataFrame, meta_cols: list[str], feature: str, threshold: float) -> pd.DataFrame:
    out = frame[meta_cols].reset_index(drop=True).copy()
    raw = pd.to_numeric(frame[feature], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    signal = np.where(raw >= threshold, 1, np.where(raw <= -threshold, -1, 0))
    out["pred_label"] = signal.astype(int)
    out["prob_down"] = np.where(signal < 0, 1.0, np.where(signal == 0, 1.0 / 3.0, 0.0))
    out["prob_flat"] = np.where(signal == 0, 1.0 / 3.0, 0.0)
    out["prob_up"] = np.where(signal > 0, 1.0, np.where(signal == 0, 1.0 / 3.0, 0.0))
    out["prob_edge"] = out["prob_up"] - out["prob_down"]
    out["prob_confidence"] = out[["prob_down", "prob_flat", "prob_up"]].max(axis=1)
    out["rule_feature"] = feature
    out["signal_threshold"] = float(threshold)
    return out


def _aggregate(folds_df: pd.DataFrame, oof: pd.DataFrame, stress: pd.DataFrame, gate: dict[str, object]) -> dict[str, object]:
    out: dict[str, object] = {}
    for col in ["valid_trades", "valid_hit_rate", "valid_mean_net_pnl_bps", "valid_total_net_pnl_bps", "valid_max_drawdown_bps", "bootstrap_mean_p05_bps", "bootstrap_prob_mean_gt_0"]:
        if col in folds_df.columns:
            out[f"{col}_mean"] = _finite_mean(folds_df[col])
            out[f"{col}_min"] = _finite_min(folds_df[col])
    if not oof.empty:
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


def write_rule_taker_report(path: str | Path, result: dict[str, object], folds_df: pd.DataFrame, stress: pd.DataFrame) -> None:
    lines = [
        "# V05 Rule Taker Walk-forward Report",
        "",
        f"Rows after labels: {result.get('rows_dataset')}",
        f"Horizon seconds: {result.get('horizon_sec')}",
        f"Cost bps: {result.get('cost_bps')}",
        f"Latency seconds: {result.get('latency_sec')}",
        "",
        "## Fold metrics",
        "",
    ]
    cols = ["fold", "selected_rule_feature", "selected_signal_threshold", "valid_trades", "valid_hit_rate", "valid_mean_net_pnl_bps", "valid_total_net_pnl_bps", "bootstrap_mean_p05_bps"]
    existing = [c for c in cols if c in folds_df.columns]
    lines.append(folds_df[existing].to_markdown(index=False) if not folds_df.empty else "No folds.")
    lines.extend(["", "## Aggregate", "", "```json", json.dumps(result.get("aggregate", {}), indent=2), "```", ""])
    lines.extend(["## Robust profit gate", "", "```json", json.dumps(result.get("profit_gate", {}), indent=2), "```", ""])
    if not stress.empty:
        cols2 = ["cost_bps", "latency_sec", "edge_threshold", "trades", "hit_rate", "mean_net_pnl_bps", "total_net_pnl_bps"]
        lines.extend(["## Stress sweep", "", stress[cols2].head(20).to_markdown(index=False), ""])
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
