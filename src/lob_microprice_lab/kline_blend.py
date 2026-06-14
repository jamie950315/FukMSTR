from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd


PROB_COLS = ["prob_down", "prob_flat", "prob_up"]


def run_kline_blend_ensemble(
    *,
    base_ensemble_dir: str | Path,
    kline_ensemble_dir: str | Path,
    out_dir: str | Path,
    kline_alpha: float = 0.1,
    keep_kline_feature_columns: bool = True,
    clean: bool = False,
) -> dict[str, object]:
    """Blend a v12 base ensemble with a K-line-augmented ensemble.

    `kline_alpha` is the fixed contribution of the K-line-trained model:
    blended_prob = (1 - alpha) * base_prob + alpha * kline_prob.
    This produces a normal ensemble directory that can be passed to slot-veto-audit.
    """
    base = Path(base_ensemble_dir)
    kline = Path(kline_ensemble_dir)
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    alpha = float(kline_alpha)
    if not 0.0 <= alpha <= 1.0:
        raise ValueError("kline_alpha must be between 0 and 1")
    fold_rows: list[dict[str, object]] = []
    for base_fold in sorted([p for p in base.glob("fold_*") if p.is_dir()]):
        fold = _fold_num(base_fold)
        kline_fold = kline / f"fold_{fold:02d}"
        if not kline_fold.exists():
            raise FileNotFoundError(f"missing K-line fold directory: {kline_fold}")
        out_fold = out / f"fold_{fold:02d}"
        out_fold.mkdir(parents=True, exist_ok=True)
        for name in ["calibration_predictions.csv", "validation_predictions.csv"]:
            base_df = pd.read_csv(base_fold / name)
            kline_df = pd.read_csv(kline_fold / name)
            blended = blend_prediction_frames(base_df, kline_df, kline_alpha=alpha)
            if not keep_kline_feature_columns:
                drop_cols = [c for c in blended.columns if c.startswith("kline_") and c != "kline_blend_alpha"]
                blended = blended.drop(columns=drop_cols, errors="ignore")
            blended.to_csv(out_fold / name, index=False)
        # Copy non-prediction diagnostics when available.
        for name in ["selected_features.csv", "calibration_taker_sweep.csv", "validation_taker_backtest.csv"]:
            src = kline_fold / name
            if src.exists():
                shutil.copy2(src, out_fold / name)
        fold_rows.append({"fold": fold, "rows_calibration": int(len(pd.read_csv(out_fold / "calibration_predictions.csv"))), "rows_validation": int(len(pd.read_csv(out_fold / "validation_predictions.csv")))})
    for name in ["config_resolved.yaml", "kline_feature_audit.json"]:
        src = kline / name
        if src.exists():
            shutil.copy2(src, out / name)
    result = {
        "base_ensemble_dir": str(base),
        "kline_ensemble_dir": str(kline),
        "kline_alpha": alpha,
        "keep_kline_feature_columns": bool(keep_kline_feature_columns),
        "folds": fold_rows,
        "out_dir": str(out),
    }
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_blend_report(out / "REPORT.md", result)
    return result


def blend_prediction_frames(base_df: pd.DataFrame, kline_df: pd.DataFrame, *, kline_alpha: float) -> pd.DataFrame:
    if not set(PROB_COLS).issubset(base_df.columns) or not set(PROB_COLS).issubset(kline_df.columns):
        raise ValueError("both prediction frames must contain prob_down, prob_flat, prob_up")
    left = base_df.copy().reset_index(drop=True)
    right = kline_df.copy().reset_index(drop=True)
    if "timestamp" in left.columns and "timestamp" in right.columns:
        merged = right.merge(left[["timestamp"] + PROB_COLS], on="timestamp", how="inner", suffixes=("", "_base"))
        if len(merged) != len(right) or len(merged) != len(left):
            raise ValueError("base and K-line predictions do not have matching timestamps; rerun with matching fold settings")
        out = merged.copy()
        for col in PROB_COLS:
            out[col] = (1.0 - float(kline_alpha)) * pd.to_numeric(out[f"{col}_base"], errors="coerce") + float(kline_alpha) * pd.to_numeric(out[col], errors="coerce")
            out = out.drop(columns=[f"{col}_base"])
    else:
        if len(left) != len(right):
            raise ValueError("prediction frames have different lengths and no timestamp column")
        out = right.copy()
        for col in PROB_COLS:
            out[col] = (1.0 - float(kline_alpha)) * pd.to_numeric(left[col], errors="coerce").to_numpy() + float(kline_alpha) * pd.to_numeric(right[col], errors="coerce").to_numpy()
    prob_sum = out[PROB_COLS].sum(axis=1).replace(0, np.nan)
    for col in PROB_COLS:
        out[col] = (out[col] / prob_sum).fillna(1.0 / 3.0).clip(0.0, 1.0)
    out["prob_edge"] = out["prob_up"].astype(float) - out["prob_down"].astype(float)
    labels = np.asarray([-1, 0, 1], dtype=int)
    out["pred_label"] = labels[np.argmax(out[PROB_COLS].to_numpy(dtype=float), axis=1)]
    out["prob_confidence"] = out[PROB_COLS].max(axis=1)
    out["kline_blend_alpha"] = float(kline_alpha)
    return out


def write_blend_report(path: str | Path, result: dict[str, object]) -> None:
    lines = [
        "# V13 K-line Blend Ensemble",
        "",
        f"Base ensemble: `{result.get('base_ensemble_dir')}`",
        f"K-line ensemble: `{result.get('kline_ensemble_dir')}`",
        f"K-line alpha: `{result.get('kline_alpha')}`",
        "",
        "This directory keeps the v12 fold structure and blends probability outputs with a fixed K-line-trained model weight. It is intentionally a normal ensemble directory, so existing v12 tools such as `slot-veto-audit` can consume it unchanged.",
        "",
    ]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def _fold_num(path: Path) -> int:
    tag = path.name.replace("fold_", "")
    return int(tag) if tag.isdigit() else 0
