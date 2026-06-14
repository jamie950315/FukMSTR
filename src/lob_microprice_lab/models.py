from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    brier_score_loss,
    classification_report,
    confusion_matrix,
    f1_score,
    log_loss,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .config import ModelConfig

TARGET_COLUMNS = {"future_mid", "future_return_bps", "future_best_bid", "future_best_ask", "label"}
META_COLUMNS = {"timestamp", "mid", "best_bid", "best_ask", "microprice_l1"}


class RobustWinsorizer(BaseEstimator, TransformerMixin):
    """Clip features to train-set quantile bounds.

    The transformer keeps large-order information while reducing the leverage of extreme erroneous or rare values.
    """

    def __init__(self, lower: float = 0.01, upper: float = 0.99):
        self.lower = lower
        self.upper = upper

    def fit(self, X, y=None):
        arr = _to_numpy(X)
        self.lower_bounds_ = np.nanquantile(arr, self.lower, axis=0)
        self.upper_bounds_ = np.nanquantile(arr, self.upper, axis=0)
        return self

    def transform(self, X):
        arr = _to_numpy(X).copy()
        return np.clip(arr, self.lower_bounds_, self.upper_bounds_)


def _to_numpy(X) -> np.ndarray:
    if isinstance(X, pd.DataFrame):
        return X.to_numpy(dtype=float)
    return np.asarray(X, dtype=float)


def select_feature_columns(frame: pd.DataFrame) -> list[str]:
    excluded = TARGET_COLUMNS | {"timestamp", "future_mid", "future_return_bps", "label"}
    cols = []
    for col in frame.columns:
        if col in excluded or col.startswith("future_"):
            continue
        if pd.api.types.is_numeric_dtype(frame[col]):
            cols.append(col)
    return cols


def make_model(cfg: ModelConfig) -> Pipeline:
    lower, upper = cfg.quantile_clip
    model_type = cfg.type.lower().strip()
    common_steps: list[tuple[str, object]] = [
        ("winsor", RobustWinsorizer(lower=lower, upper=upper)),
        ("imputer", SimpleImputer(strategy="median")),
    ]

    if model_type in {"logistic", "logreg"}:
        clf = LogisticRegression(
            max_iter=cfg.max_iter,
            class_weight="balanced",
            random_state=cfg.random_state,
        )
        return Pipeline(common_steps + [("scaler", StandardScaler()), ("clf", clf)])

    if model_type in {"hgb", "hist_gradient_boosting"}:
        clf = HistGradientBoostingClassifier(
            random_state=cfg.random_state,
            max_iter=min(int(cfg.max_iter), 120),
            learning_rate=0.06,
            max_leaf_nodes=21,
            l2_regularization=0.05,
            early_stopping=True,
            validation_fraction=0.15,
        )
        return Pipeline(common_steps + [("clf", clf)])

    if model_type in {"rf", "random_forest"}:
        clf = RandomForestClassifier(
            n_estimators=300,
            min_samples_leaf=20,
            class_weight="balanced_subsample",
            random_state=cfg.random_state,
            n_jobs=1,
        )
        return Pipeline(common_steps + [("clf", clf)])

    if model_type in {"et", "extra_trees", "extra-trees"}:
        clf = ExtraTreesClassifier(
            n_estimators=350,
            min_samples_leaf=10,
            max_features="sqrt",
            class_weight="balanced",
            random_state=cfg.random_state,
            n_jobs=1,
        )
        return Pipeline(common_steps + [("clf", clf)])

    raise ValueError(f"unsupported model type: {cfg.type}")


def train_model(X_train: pd.DataFrame, y_train: pd.Series, cfg: ModelConfig) -> Pipeline:
    model = make_model(cfg)
    model.fit(X_train, y_train)
    return model


def predict_frame(model: Pipeline, X: pd.DataFrame, meta: pd.DataFrame) -> pd.DataFrame:
    pred = model.predict(X)
    out = meta.reset_index(drop=True).copy()
    out["pred_label"] = pred.astype(int)

    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(X)
        classes = list(model.classes_)
        for label in [-1, 0, 1]:
            if label in classes:
                out[f"prob_{_label_name(label)}"] = proba[:, classes.index(label)]
            else:
                out[f"prob_{_label_name(label)}"] = 0.0
    else:
        out["prob_down"] = (out["pred_label"] == -1).astype(float)
        out["prob_flat"] = (out["pred_label"] == 0).astype(float)
        out["prob_up"] = (out["pred_label"] == 1).astype(float)
    out["prob_edge"] = out.get("prob_up", 0.0).astype(float) - out.get("prob_down", 0.0).astype(float)
    out["prob_confidence"] = out[["prob_down", "prob_flat", "prob_up"]].max(axis=1)
    return out


def evaluate_classification(y_true: Iterable[int], y_pred: Iterable[int]) -> dict[str, object]:
    y_true_arr = np.asarray(list(y_true), dtype=int)
    y_pred_arr = np.asarray(list(y_pred), dtype=int)
    labels = [-1, 0, 1]
    accuracy = float(accuracy_score(y_true_arr, y_pred_arr))
    majority_label, majority_accuracy = _majority_baseline(y_true_arr)
    return {
        "accuracy": accuracy,
        "balanced_accuracy": float(balanced_accuracy_score(y_true_arr, y_pred_arr)),
        "macro_f1": float(f1_score(y_true_arr, y_pred_arr, labels=labels, average="macro", zero_division=0)),
        "majority_label_valid": int(majority_label),
        "majority_accuracy_valid": float(majority_accuracy),
        "accuracy_lift_vs_majority": float(accuracy - majority_accuracy),
        "confusion_matrix_labels": labels,
        "confusion_matrix": confusion_matrix(y_true_arr, y_pred_arr, labels=labels).tolist(),
        "classification_report": classification_report(
            y_true_arr,
            y_pred_arr,
            labels=labels,
            target_names=["down", "flat", "up"],
            zero_division=0,
            output_dict=True,
        ),
    }


def evaluate_probabilities(y_true: Iterable[int], predictions: pd.DataFrame, bins: int = 10) -> dict[str, object]:
    """Evaluate probability quality for the tri-class up/flat/down prediction frame."""
    y = np.asarray(list(y_true), dtype=int)
    prob_cols = ["prob_down", "prob_flat", "prob_up"]
    if any(col not in predictions.columns for col in prob_cols) or len(y) == 0:
        return {}
    probs = predictions[prob_cols].astype(float).to_numpy()
    # Normalize defensively in case a downstream model produces rounded values.
    row_sum = probs.sum(axis=1, keepdims=True)
    probs = np.divide(probs, row_sum, out=np.full_like(probs, 1.0 / 3.0), where=row_sum != 0)
    labels = np.array([-1, 0, 1])
    class_to_index = {label: i for i, label in enumerate(labels)}
    y_index = np.array([class_to_index[int(v)] for v in y])

    out: dict[str, object] = {}
    try:
        out["log_loss"] = float(log_loss(y_index, probs, labels=[0, 1, 2]))
    except Exception:
        out["log_loss"] = 0.0
    for label, col in zip(labels, prob_cols):
        try:
            out[f"brier_{_label_name(int(label))}"] = float(brier_score_loss((y == label).astype(int), predictions[col].astype(float)))
        except Exception:
            out[f"brier_{_label_name(int(label))}"] = 0.0
    out["ece_pred_label"] = expected_calibration_error(y, predictions, bins=bins)
    return out


def expected_calibration_error(y_true: np.ndarray, predictions: pd.DataFrame, bins: int = 10) -> float:
    prob_cols = ["prob_down", "prob_flat", "prob_up"]
    probs = predictions[prob_cols].astype(float).to_numpy()
    labels = np.array([-1, 0, 1])
    confidence = probs.max(axis=1)
    predicted = labels[probs.argmax(axis=1)]
    correct = (predicted == y_true).astype(float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (confidence >= lo) & (confidence < hi if hi < 1.0 else confidence <= hi)
        if not np.any(mask):
            continue
        ece += float(mask.mean()) * abs(float(correct[mask].mean()) - float(confidence[mask].mean()))
    return float(ece)


def feature_importance_frame(model: Pipeline, feature_columns: list[str], top_n: int = 30) -> pd.DataFrame:
    """Return coefficient/importances for models that expose them."""
    clf = model.named_steps.get("clf") if isinstance(model, Pipeline) else model
    if clf is None:
        return pd.DataFrame(columns=["feature", "importance"])
    values: np.ndarray | None = None
    if hasattr(clf, "coef_"):
        coef = np.asarray(clf.coef_, dtype=float)
        values = np.abs(coef).mean(axis=0) if coef.ndim == 2 else np.abs(coef)
    elif hasattr(clf, "estimators_") and all(hasattr(est, "coef_") for est in clf.estimators_):
        coef = np.vstack([np.asarray(est.coef_, dtype=float).reshape(1, -1) for est in clf.estimators_])
        values = np.abs(coef).mean(axis=0)
    elif hasattr(clf, "feature_importances_"):
        values = np.asarray(clf.feature_importances_, dtype=float)
    if values is None or len(values) != len(feature_columns):
        return pd.DataFrame(columns=["feature", "importance"])
    out = pd.DataFrame({"feature": feature_columns, "importance": values})
    out = out.sort_values("importance", ascending=False).head(top_n).reset_index(drop=True)
    return out


def _majority_baseline(y_true_arr: np.ndarray) -> tuple[int, float]:
    if len(y_true_arr) == 0:
        return 0, 0.0
    values, counts = np.unique(y_true_arr, return_counts=True)
    idx = int(np.argmax(counts))
    return int(values[idx]), float(counts[idx] / len(y_true_arr))


def save_model_artifacts(model: Pipeline, feature_columns: list[str], out_dir: str | Path) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out / "model.joblib")
    (out / "feature_columns.json").write_text(json.dumps(feature_columns, indent=2), encoding="utf-8")


def load_model_artifacts(run_dir: str | Path) -> tuple[Pipeline, list[str]]:
    run = Path(run_dir)
    model = joblib.load(run / "model.joblib")
    feature_columns = json.loads((run / "feature_columns.json").read_text(encoding="utf-8"))
    return model, feature_columns


def _label_name(label: int) -> str:
    return {1: "up", 0: "flat", -1: "down"}[label]
