from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, RidgeClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .fixed_template import load_ensemble_fold_predictions
from .selective import (
    aggregate_selective_folds,
    backtest_fixed_signals_taker_bidask_non_overlapping,
    backtest_selective_taker_bidask_non_overlapping,
    fixed_signal_robust_gate,
    search_selective_candidates,
    shift_null_fixed_signals,
    stress_fixed_signals,
    summarize_shift_null,
    SelectiveCandidate,
)
from .stress import block_bootstrap_pnl

DEFAULT_CALIBRATOR_FEATURES = [
    "prob_edge_raw",
    "prob_confidence",
    "spread_bps",
    "imbalance_l3",
    "imbalance_l5",
    "microprice_dev_bps_l3",
    "microprice_dev_bps_l5",
    "ofi_sum_l3_norm",
    "ofi_sum_l5_norm",
    "mid_ret_60r_bps",
    "mid_vol_60r_bps",
]


def run_calibrated_edge_audit(
    *,
    ensemble_dir: str | Path,
    out_dir: str | Path,
    horizon_sec: float,
    cost_bps: float = 1.5,
    latency_sec: float = 0.5,
    calibrator: str = "logistic",
    calibrator_features: list[str] | None = None,
    edge_thresholds: list[float] | None = None,
    signed_columns: list[str] | None = None,
    spread_quantiles: list[float] | None = None,
    vol_modes: list[str] | None = None,
    min_calibration_trades: int = 8,
    min_train_labels: int = 50,
    stress_cost_bps_values: list[float] | None = None,
    stress_latency_sec_values: list[float] | None = None,
    shift_null_runs: int = 80,
    clean: bool = False,
) -> dict[str, object]:
    """Calibrate model probability edge on past data, then run V07-style selective filters.

    The raw ensemble may be systematically inverted at long horizons.  This postprocessor learns a
    fold-local mapping from current features to up/down probability using calibration rows only.
    It then replaces prob_up/prob_down on both calibration and validation frames and applies the
    existing selective search on the calibrated edge.
    """
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    calibrator_features = calibrator_features or DEFAULT_CALIBRATOR_FEATURES
    edge_thresholds = edge_thresholds or [0.05, 0.1, 0.2, 0.3, 0.5]
    spread_quantiles = spread_quantiles or [1.0]
    vol_modes = vol_modes or ["none"]
    stress_cost_bps_values = stress_cost_bps_values or [1.5, 3.0, 5.0]
    stress_latency_sec_values = stress_latency_sec_values or [0.0, 0.5, 1.0, 2.0]

    folds = load_ensemble_fold_predictions(ensemble_dir)
    fold_rows: list[dict[str, object]] = []
    candidate_rows: list[pd.DataFrame] = []
    validation_frames: list[pd.DataFrame] = []
    coefficient_rows: list[dict[str, object]] = []

    for fold_num, calibration_raw, validation_raw in folds:
        calibration, validation, model_info = _fit_apply_edge_calibrator(
            calibration_raw,
            validation_raw,
            features=calibrator_features,
            calibrator=calibrator,
            min_train_labels=min_train_labels,
        )
        coefficient_rows.extend({"fold": fold_num, **row} for row in model_info.pop("feature_coefficients", []))

        candidates = search_selective_candidates(
            calibration,
            edge_thresholds=edge_thresholds,
            cost_bps=cost_bps,
            horizon_sec=horizon_sec,
            latency_sec=latency_sec,
            min_trades=min_calibration_trades,
            signed_columns=signed_columns,
            spread_quantiles=spread_quantiles,
            vol_modes=vol_modes,
        )
        if candidates.empty:
            raise ValueError(f"no calibrated selective candidates generated for fold {fold_num}")
        selected = SelectiveCandidate.from_dict(json.loads(str(candidates.iloc[0]["candidate_json"])))
        candidates.insert(0, "fold", fold_num)
        candidate_rows.append(candidates)

        bt, metrics = backtest_selective_taker_bidask_non_overlapping(
            validation,
            candidate=selected,
            cost_bps=cost_bps,
            horizon_sec=horizon_sec,
            latency_sec=latency_sec,
        )
        if "fold" in bt.columns:
            bt["fold"] = fold_num
        else:
            bt.insert(0, "fold", fold_num)
        bt["edge_calibrator"] = calibrator
        bt["selected_candidate_json"] = json.dumps(selected.to_dict(), sort_keys=True)
        validation_frames.append(bt)

        trades = bt.loc[bt["traded"] == 1, "net_pnl_bps"] if "traded" in bt.columns else pd.Series(dtype=float)
        boot = block_bootstrap_pnl(trades, iterations=500, block_size=10, seed=40900 + int(fold_num))
        fold_rows.append(
            {
                "fold": fold_num,
                **model_info,
                "calibration_candidates": int(len(candidates)),
                "selected_candidate_json": json.dumps(selected.to_dict(), sort_keys=True),
                "selected_edge_threshold": float(selected.edge_threshold),
                "selected_direction_mode": selected.direction_mode,
                "selected_signed_col": selected.signed_col,
                "selected_signed_mode": selected.signed_mode,
                "selected_signed_abs_threshold": float(selected.signed_abs_threshold or 0.0),
                "selected_spread_max_bps": selected.spread_max_bps,
                "selected_vol_mode": selected.vol_mode,
                "valid_trades": float(metrics.get("trades", 0.0)),
                "valid_hit_rate": float(metrics.get("hit_rate", 0.0)),
                "valid_mean_net_pnl_bps": float(metrics.get("mean_net_pnl_bps", 0.0)),
                "valid_total_net_pnl_bps": float(metrics.get("total_net_pnl_bps", 0.0)),
                "valid_max_drawdown_bps": float(metrics.get("max_drawdown_bps", 0.0)),
                "bootstrap_mean_p05_bps": float(boot.get("mean_p05_bps", 0.0)),
                "bootstrap_prob_mean_gt_0": float(boot.get("prob_mean_gt_0", 0.0)),
            }
        )

    folds_df = pd.DataFrame(fold_rows)
    candidates_df = pd.concat(candidate_rows, ignore_index=True) if candidate_rows else pd.DataFrame()
    oof = pd.concat(validation_frames, ignore_index=True) if validation_frames else pd.DataFrame()
    coefficients = pd.DataFrame(coefficient_rows)

    folds_df.to_csv(out / "fold_metrics.csv", index=False)
    candidates_df.to_csv(out / "calibrated_calibration_candidates.csv", index=False)
    oof.to_csv(out / "oof_calibrated_edge_backtest.csv", index=False)
    coefficients.to_csv(out / "calibrator_coefficients.csv", index=False)

    stress = stress_fixed_signals(
        oof,
        horizon_sec=horizon_sec,
        cost_bps_values=stress_cost_bps_values,
        latency_sec_values=stress_latency_sec_values,
    ) if not oof.empty else pd.DataFrame()
    stress.to_csv(out / "oof_fixed_signal_stress.csv", index=False)
    robust_gate = fixed_signal_robust_gate(stress, min_trades=max(1, min_calibration_trades)) if not stress.empty else {"passed": False, "reason": "empty stress"}

    actual_repriced, actual_metrics = backtest_fixed_signals_taker_bidask_non_overlapping(
        oof,
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
    ) if not oof.empty else (pd.DataFrame(), {})
    actual_repriced.to_csv(out / "oof_primary_repriced_backtest.csv", index=False)
    shift_null = shift_null_fixed_signals(
        oof,
        horizon_sec=horizon_sec,
        cost_bps=cost_bps,
        latency_sec=latency_sec,
        shifts=shift_null_runs,
    ) if not oof.empty else pd.DataFrame()
    shift_null.to_csv(out / "shift_null_fixed_signals.csv", index=False)
    shift_summary = summarize_shift_null(actual_metrics, shift_null)

    aggregate = aggregate_selective_folds(folds_df, oof, stress, robust_gate)
    aggregate.update({f"shift_null_{k}": v for k, v in shift_summary.items()})
    gate = _evaluate_calibrated_gate(aggregate, robust_gate, min_calibration_trades=min_calibration_trades)
    result = {
        "source_ensemble_dir": str(ensemble_dir),
        "horizon_sec": float(horizon_sec),
        "cost_bps": float(cost_bps),
        "latency_sec": float(latency_sec),
        "calibrator": calibrator,
        "calibrator_features": list(calibrator_features),
        "edge_thresholds": [float(x) for x in edge_thresholds],
        "signed_columns": signed_columns,
        "spread_quantiles": [float(x) for x in spread_quantiles],
        "vol_modes": list(vol_modes),
        "min_calibration_trades": int(min_calibration_trades),
        "min_train_labels": int(min_train_labels),
        "aggregate": aggregate,
        "robust_gate": robust_gate,
        "gate": gate,
        "out_dir": str(out),
    }
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    _write_report(out / "REPORT.md", result, folds_df, stress, coefficients)
    return result


def _fit_apply_edge_calibrator(
    calibration: pd.DataFrame,
    validation: pd.DataFrame,
    *,
    features: list[str],
    calibrator: str,
    min_train_labels: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    cal = calibration.copy()
    val = validation.copy()
    for frame in (cal, val):
        raw_edge = pd.to_numeric(frame.get("prob_up", 0.0), errors="coerce").fillna(0.0) - pd.to_numeric(frame.get("prob_down", 0.0), errors="coerce").fillna(0.0)
        frame["prob_edge_raw"] = raw_edge
    usable_features = [c for c in features if c in cal.columns and c in val.columns and not c.startswith("future_")]
    if not usable_features:
        usable_features = ["prob_edge_raw"]
    labels = pd.to_numeric(cal.get("label", pd.Series(np.zeros(len(cal)))), errors="coerce").fillna(0).astype(int)
    train_mask = labels != 0
    info: dict[str, object] = {
        "calibrator_used": "raw_edge_fallback",
        "calibrator_train_rows": int(train_mask.sum()),
        "calibrator_feature_count": int(len(usable_features)),
        "calibrator_train_up_rate": float((labels[train_mask] > 0).mean()) if int(train_mask.sum()) else 0.0,
    }
    if int(train_mask.sum()) < int(min_train_labels) or labels[train_mask].nunique() < 2:
        cal_out = _assign_raw_edge_probability(cal)
        val_out = _assign_raw_edge_probability(val)
        info["feature_coefficients"] = []
        return cal_out, val_out, info

    X = cal.loc[train_mask, usable_features]
    y = (labels.loc[train_mask] > 0).astype(int)
    if calibrator == "ridge":
        estimator = RidgeClassifier(class_weight="balanced", alpha=1.0)
    elif calibrator == "logistic":
        estimator = LogisticRegression(max_iter=1000, class_weight="balanced", C=0.5, solver="lbfgs")
    else:
        raise ValueError("calibrator must be logistic or ridge")
    pipe = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler()), ("model", estimator)])
    pipe.fit(X, y)
    if calibrator == "logistic":
        p_cal = pipe.predict_proba(cal[usable_features])[:, 1]
        p_val = pipe.predict_proba(val[usable_features])[:, 1]
        coefs = np.ravel(pipe.named_steps["model"].coef_)
    else:
        score_cal = pipe.decision_function(cal[usable_features])
        score_val = pipe.decision_function(val[usable_features])
        p_cal = 1.0 / (1.0 + np.exp(-np.clip(score_cal, -20, 20)))
        p_val = 1.0 / (1.0 + np.exp(-np.clip(score_val, -20, 20)))
        coefs = np.ravel(pipe.named_steps["model"].coef_)
    cal_out = _assign_calibrated_probability(cal, p_cal)
    val_out = _assign_calibrated_probability(val, p_val)
    info["calibrator_used"] = calibrator
    info["calibrator_features"] = ",".join(usable_features)
    info["calibrator_train_accuracy"] = float((pipe.predict(X) == y).mean())
    info["calibrator_train_prob_mean"] = float(np.mean(p_cal))
    info["calibrator_valid_prob_mean"] = float(np.mean(p_val))
    info["feature_coefficients"] = [
        {"feature": f, "coefficient": float(c)} for f, c in sorted(zip(usable_features, coefs), key=lambda item: abs(float(item[1])), reverse=True)
    ]
    return cal_out, val_out, info


def _assign_raw_edge_probability(frame: pd.DataFrame) -> pd.DataFrame:
    edge = pd.to_numeric(frame["prob_edge_raw"], errors="coerce").fillna(0.0).clip(-1.0, 1.0)
    p_up = ((edge + 1.0) / 2.0).clip(0.0, 1.0)
    return _assign_calibrated_probability(frame, p_up)


def _assign_calibrated_probability(frame: pd.DataFrame, p_up: np.ndarray | pd.Series) -> pd.DataFrame:
    out = frame.copy()
    p = pd.Series(p_up, index=out.index).astype(float).clip(0.001, 0.999)
    out["prob_up_raw_model"] = out.get("prob_up", np.nan)
    out["prob_down_raw_model"] = out.get("prob_down", np.nan)
    out["prob_up"] = p
    out["prob_down"] = 1.0 - p
    out["prob_flat"] = 0.0
    out["prob_edge_calibrated"] = out["prob_up"] - out["prob_down"]
    out["prob_confidence"] = np.maximum(out["prob_up"], out["prob_down"])
    return out


def _evaluate_calibrated_gate(aggregate: dict[str, object], robust_gate: dict[str, object], *, min_calibration_trades: int) -> dict[str, object]:
    checks = {
        "enough_oof_trades": float(aggregate.get("oof_trades", 0)) >= 20.0,
        "enough_min_fold_trades": float(aggregate.get("valid_trades_min", 0.0)) >= max(3.0, float(min_calibration_trades) / 2.0),
        "positive_oof_mean": float(aggregate.get("oof_mean_net_pnl_bps", -999.0)) > 0.0,
        "positive_fold_min_mean": float(aggregate.get("valid_mean_net_pnl_bps_min", -999.0)) > 0.0,
        "positive_bootstrap_p05_min": float(aggregate.get("bootstrap_mean_p05_bps_min", -999.0)) > 0.0,
        "robust_stress_gate": bool(robust_gate.get("passed")),
        "shift_null_mean_ok": float(aggregate.get("shift_null_p_null_mean_ge_actual", 1.0)) <= 0.10,
        "shift_null_total_ok": float(aggregate.get("shift_null_p_null_total_ge_actual", 1.0)) <= 0.10,
    }
    failed = [name for name, ok in checks.items() if not ok]
    return {"passed": not failed, "failed_checks": failed, "checks": checks}


def _write_report(path: str | Path, result: dict[str, object], folds: pd.DataFrame, stress: pd.DataFrame, coefficients: pd.DataFrame) -> None:
    lines = [
        "# Research V09 Calibrated-edge Audit",
        "",
        "This audit learns a fold-local probability-edge mapping on calibration rows only, then applies selective trading to the future validation fold.",
        "The goal is to test whether the long-horizon inverted-edge diagnostic can be converted into an explicitly calibrated signal.",
        "",
        "## Settings",
        "",
        "```json",
        json.dumps({k: result.get(k) for k in ["source_ensemble_dir", "horizon_sec", "cost_bps", "latency_sec", "calibrator", "calibrator_features", "edge_thresholds", "signed_columns", "spread_quantiles", "vol_modes"]}, indent=2),
        "```",
        "",
        "## Aggregate",
        "",
        "```json",
        json.dumps(result.get("aggregate", {}), indent=2),
        "```",
        "",
        "## Gate",
        "",
        "```json",
        json.dumps(result.get("gate", {}), indent=2),
        "```",
        "",
        "## Fold metrics",
        "",
    ]
    fold_cols = [
        "fold",
        "calibrator_used",
        "calibrator_train_rows",
        "calibrator_train_accuracy",
        "selected_edge_threshold",
        "selected_direction_mode",
        "selected_signed_col",
        "selected_signed_mode",
        "selected_signed_abs_threshold",
        "valid_trades",
        "valid_hit_rate",
        "valid_mean_net_pnl_bps",
        "valid_total_net_pnl_bps",
        "bootstrap_mean_p05_bps",
    ]
    lines.append(folds[[c for c in fold_cols if c in folds.columns]].to_markdown(index=False) if not folds.empty else "No folds.")
    lines.extend(["", "## Top calibrator coefficients", ""])
    if coefficients.empty:
        lines.append("No coefficients.")
    else:
        top = coefficients.reindex(coefficients["coefficient"].abs().sort_values(ascending=False).index).head(20)
        lines.append(top.to_markdown(index=False))
    lines.extend(["", "## Stress", ""])
    stress_cols = ["cost_bps", "latency_sec", "trades", "hit_rate", "mean_net_pnl_bps", "total_net_pnl_bps", "max_drawdown_bps"]
    lines.append(stress[[c for c in stress_cols if c in stress.columns]].to_markdown(index=False) if not stress.empty else "No stress rows.")
    lines.extend(["", "## Interpretation", "", "Passing this audit would mean calibration-only signal correction produces a cost- and latency-robust long-horizon edge. Failing means the inverted-edge observation remains a diagnostic artifact or requires more data."])
    Path(path).write_text("\n".join(lines), encoding="utf-8")
