from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from .config import AppConfig
from .data_schema import infer_depth, read_csv, timestamps_to_ns
from .features import build_features
from .labels import add_future_labels
from .models import select_feature_columns
from .pipeline import chronological_split


def profile_market_data(
    *,
    book_path: str | Path,
    trades_path: str | Path | None,
    config_path: str | Path | None,
    out_dir: str | Path,
) -> dict[str, object]:
    """Profile book quality, sampling gaps, spread, and short mid-price moves."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cfg = AppConfig.from_yaml(config_path)
    book = read_csv(book_path)
    trades = read_csv(trades_path) if trades_path else None
    features = build_features(book, trades=trades, cfg=cfg.features, timestamp_col=cfg.io.timestamp_col)

    ns = timestamps_to_ns(features["timestamp"])
    diffs = np.diff(ns)
    diffs = diffs[diffs > 0]
    step_sec = diffs / 1_000_000_000 if len(diffs) else np.array([], dtype=float)
    one_step_return = features["mid"].pct_change().fillna(0.0) * 10000.0
    move = one_step_return.to_numpy(dtype=float)
    feature_columns = select_feature_columns(features)

    profile: dict[str, object] = {
        "book_path": str(book_path),
        "trades_path": str(trades_path) if trades_path else None,
        "rows_raw_book": int(len(book)),
        "rows_features": int(len(features)),
        "depth": int(infer_depth(book)),
        "start_timestamp": str(features["timestamp"].iloc[0]) if len(features) else None,
        "end_timestamp": str(features["timestamp"].iloc[-1]) if len(features) else None,
        "duration_sec": float((ns[-1] - ns[0]) / 1_000_000_000) if len(ns) > 1 else 0.0,
        "median_step_sec": float(np.median(step_sec)) if len(step_sec) else 0.0,
        "p95_step_sec": float(np.quantile(step_sec, 0.95)) if len(step_sec) else 0.0,
        "mid_move_rate": float(np.mean(move != 0)) if len(move) else 0.0,
        "up_move_rate": float(np.mean(move > 0)) if len(move) else 0.0,
        "down_move_rate": float(np.mean(move < 0)) if len(move) else 0.0,
        "feature_count": int(len(feature_columns)),
    }
    profile.update(_describe_series(features["mid"], "mid"))
    profile.update(_describe_series(features["spread_bps"], "spread_bps"))
    profile.update(_describe_series(one_step_return.abs(), "one_step_abs_return_bps"))
    profile.update(_describe_series(one_step_return, "one_step_return_bps"))
    if "microprice_dev_bps" in features.columns:
        profile.update(_describe_series(features["microprice_dev_bps"], "microprice_dev_bps"))

    (out / "market_profile.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
    lines = [
        "# Market Profile",
        "",
        f"Book path: `{profile['book_path']}`",
        f"Rows: {profile['rows_features']}",
        f"Depth: {profile['depth']}",
        f"Time range: {profile['start_timestamp']} to {profile['end_timestamp']}",
        f"Median step seconds: {profile['median_step_sec']}",
        f"Spread bps median: {profile['spread_bps_median']}",
        f"One-step abs return bps mean: {profile['one_step_abs_return_bps_mean']}",
        f"Mid move rate: {profile['mid_move_rate']}",
        f"Feature count: {profile['feature_count']}",
        "",
        "This profile is a data-quality and regime check before modeling.",
    ]
    (out / "MARKET_PROFILE.md").write_text("\n".join(lines), encoding="utf-8")
    return profile


def feature_forward_scan(
    *,
    book_path: str | Path,
    trades_path: str | Path | None,
    config_path: str | Path | None,
    out_dir: str | Path,
    horizons_sec: list[float],
    threshold_bps: float = 1.0,
    top_n: int = 40,
) -> dict[str, object]:
    """Rank numeric features by correlation with future mid-price returns across horizons."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cfg = AppConfig.from_yaml(config_path)
    book = read_csv(book_path)
    trades = read_csv(trades_path) if trades_path else None
    features = build_features(book, trades=trades, cfg=cfg.features, timestamp_col=cfg.io.timestamp_col)
    feature_columns = select_feature_columns(features)

    records: list[dict[str, object]] = []
    labels: list[dict[str, object]] = []
    for horizon in horizons_sec:
        dataset = add_future_labels(features, horizon_sec=float(horizon), threshold_bps=float(threshold_bps))
        y = pd.to_numeric(dataset["future_return_bps"], errors="coerce")
        counts = dataset["label"].value_counts().to_dict()
        labels.append(
            {
                "horizon_sec": float(horizon),
                "rows": int(len(dataset)),
                "threshold_bps": float(threshold_bps),
                "down": int(counts.get(-1, 0)),
                "flat": int(counts.get(0, 0)),
                "up": int(counts.get(1, 0)),
                "mean_abs_future_return_bps": float(y.abs().mean()) if len(y) else 0.0,
                "std_future_return_bps": float(y.std(ddof=1)) if len(y) > 1 else 0.0,
            }
        )
        for col in feature_columns:
            x = pd.to_numeric(dataset[col], errors="coerce")
            tmp = pd.DataFrame({"x": x, "y": y}).replace([np.inf, -np.inf], np.nan).dropna()
            if len(tmp) < 30 or tmp["x"].nunique() <= 1:
                continue
            pearson = _corr(tmp["x"], tmp["y"], "pearson")
            spearman = _corr(tmp["x"], tmp["y"], "spearman")
            records.append(
                {
                    "horizon_sec": float(horizon),
                    "feature": col,
                    "pearson": pearson,
                    "spearman": spearman,
                    "abs_pearson": abs(pearson),
                    "abs_spearman": abs(spearman),
                    "sign_accuracy": _sign_accuracy(tmp["x"], tmp["y"]),
                    "rows": int(len(tmp)),
                }
            )

    scan = pd.DataFrame(records)
    if not scan.empty:
        scan = scan.sort_values(["horizon_sec", "abs_spearman", "abs_pearson"], ascending=[True, False, False]).reset_index(drop=True)
    label_df = pd.DataFrame(labels)
    scan.to_csv(out / "feature_forward_scan.csv", index=False)
    label_df.to_csv(out / "label_summary.csv", index=False)

    lines = [
        "# Feature Forward Scan",
        "",
        f"Book path: `{book_path}`",
        f"Rows features: {len(features)}",
        f"Feature count: {len(feature_columns)}",
        f"Threshold bps: {threshold_bps}",
        "",
        "## Label summary",
        "",
        label_df.to_markdown(index=False) if not label_df.empty else "No labels.",
        "",
    ]
    for horizon in horizons_sec:
        top = scan[scan["horizon_sec"] == float(horizon)].head(top_n) if not scan.empty else pd.DataFrame()
        lines.extend([
            f"## Top features, horizon {horizon:g}s",
            "",
            top[["feature", "pearson", "spearman", "sign_accuracy", "rows"]].to_markdown(index=False) if not top.empty else "No features.",
            "",
        ])
    lines.append("Use this scan as a weak-signal triage tool. Final claims should come from chronological and walk-forward validation.")
    (out / "FEATURE_SCAN.md").write_text("\n".join(lines), encoding="utf-8")
    return {
        "rows_features": int(len(features)),
        "feature_count": int(len(feature_columns)),
        "horizons_sec": [float(x) for x in horizons_sec],
        "out_dir": str(out),
        "top_features": scan.head(int(top_n)).to_dict(orient="records") if not scan.empty else [],
    }


def feature_correlation_report(
    *,
    book_path: str | Path,
    trades_path: str | Path | None,
    config_path: str | Path | None,
    out_dir: str | Path,
    top_n: int = 40,
    clean: bool = False,
) -> dict[str, object]:
    """Rank features by train/validation correlation with the configured future return."""
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    cfg = AppConfig.from_yaml(config_path)
    book = read_csv(book_path)
    trades = read_csv(trades_path) if trades_path else None
    features = build_features(book, trades=trades, cfg=cfg.features, timestamp_col=cfg.io.timestamp_col)
    dataset = add_future_labels(features, horizon_sec=cfg.labels.horizon_sec, threshold_bps=cfg.labels.threshold_bps)
    train_df, valid_df = chronological_split(dataset, cfg.split.train_ratio)
    feature_columns = select_feature_columns(dataset)

    records: list[dict[str, object]] = []
    for col in feature_columns:
        train_s = _corr(train_df[col], train_df["future_return_bps"], "spearman")
        valid_s = _corr(valid_df[col], valid_df["future_return_bps"], "spearman")
        record = {
            "feature": col,
            "train_pearson": _corr(train_df[col], train_df["future_return_bps"], "pearson"),
            "valid_pearson": _corr(valid_df[col], valid_df["future_return_bps"], "pearson"),
            "train_spearman": train_s,
            "valid_spearman": valid_s,
            "train_sign_accuracy": _sign_accuracy(train_df[col], train_df["future_return_bps"]),
            "valid_sign_accuracy": _sign_accuracy(valid_df[col], valid_df["future_return_bps"]),
            "valid_non_null": int(pd.to_numeric(valid_df[col], errors="coerce").notna().sum()),
            "abs_valid_spearman": abs(valid_s),
            "spearman_stability": train_s * valid_s,
        }
        records.append(record)

    corr = pd.DataFrame(records).sort_values(["abs_valid_spearman", "spearman_stability"], ascending=[False, False]).reset_index(drop=True)
    corr.to_csv(out / "feature_correlations.csv", index=False)
    summary = {
        "book_path": str(book_path),
        "trades_path": str(trades_path) if trades_path else None,
        "rows_features": int(len(features)),
        "rows_dataset": int(len(dataset)),
        "rows_train": int(len(train_df)),
        "rows_valid": int(len(valid_df)),
        "feature_count": int(len(feature_columns)),
        "top_features": corr.head(int(top_n)).to_dict(orient="records"),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_correlation_markdown(out / "REPORT.md", summary, corr, top_n=top_n)
    return summary


def run_feature_diagnostics(
    *,
    book_path: str | Path,
    trades_path: str | Path | None,
    config_path: str | Path | None,
    out_dir: str | Path,
    top_n: int = 60,
    clean: bool = False,
) -> dict[str, object]:
    """Write profile, horizon scan, and configured train/validation correlation reports."""
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    profile = profile_market_data(book_path=book_path, trades_path=trades_path, config_path=config_path, out_dir=out / "profile")
    scan = feature_forward_scan(
        book_path=book_path,
        trades_path=trades_path,
        config_path=config_path,
        out_dir=out / "feature_scan",
        horizons_sec=[1.0, 5.0, 10.0],
        threshold_bps=1.0,
        top_n=top_n,
    )
    corr = feature_correlation_report(
        book_path=book_path,
        trades_path=trades_path,
        config_path=config_path,
        out_dir=out / "correlations",
        top_n=top_n,
        clean=False,
    )
    summary = {
        "rows_dataset": int(corr.get("rows_dataset", 0)),
        "feature_count": int(scan.get("feature_count", 0)),
        "profile": profile,
        "scan": scan,
        "correlations": corr,
        "top_features": corr.get("top_features", [])[:top_n],
        "out_dir": str(out),
    }
    (out / "diagnostics_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = [
        "# Feature Diagnostics",
        "",
        f"Rows: {summary['rows_dataset']}",
        f"Feature count: {summary['feature_count']}",
        "",
        "See `profile/MARKET_PROFILE.md`, `feature_scan/FEATURE_SCAN.md`, and `correlations/REPORT.md`.",
    ]
    (out / "DIAGNOSTICS.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def write_correlation_markdown(path: str | Path, summary: dict[str, object], corr: pd.DataFrame, top_n: int) -> None:
    cols = [
        "feature",
        "train_spearman",
        "valid_spearman",
        "train_pearson",
        "valid_pearson",
        "valid_sign_accuracy",
        "abs_valid_spearman",
    ]
    lines = [
        "# Feature Correlation Report",
        "",
        f"Book path: `{summary.get('book_path')}`",
        f"Rows after label construction: {summary.get('rows_dataset')}",
        f"Train rows: {summary.get('rows_train')}",
        f"Validation rows: {summary.get('rows_valid')}",
        f"Feature count: {summary.get('feature_count')}",
        "",
        "## Top validation correlations",
        "",
        corr[cols].head(top_n).to_markdown(index=False) if not corr.empty else "No features.",
        "",
        "## Notes",
        "",
        "Spearman is rank-based and is less sensitive to heavy-tailed queue sizes than Pearson. Sign accuracy treats the raw feature sign as a direction rule, so it is most meaningful for signed imbalance, OFI, and microprice-deviation features.",
        "",
    ]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def _describe_series(series: pd.Series, prefix: str) -> dict[str, float]:
    arr = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if arr.empty:
        return {f"{prefix}_{name}": 0.0 for name in ["mean", "median", "std", "p05", "p95", "min", "max"]}
    return {
        f"{prefix}_mean": float(arr.mean()),
        f"{prefix}_median": float(arr.median()),
        f"{prefix}_std": float(arr.std(ddof=1)) if len(arr) > 1 else 0.0,
        f"{prefix}_p05": float(arr.quantile(0.05)),
        f"{prefix}_p95": float(arr.quantile(0.95)),
        f"{prefix}_min": float(arr.min()),
        f"{prefix}_max": float(arr.max()),
    }


def _corr(x: pd.Series, y: pd.Series, method: str) -> float:
    frame = pd.concat([pd.to_numeric(x, errors="coerce"), pd.to_numeric(y, errors="coerce")], axis=1).replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 3 or frame.iloc[:, 0].nunique() <= 1 or frame.iloc[:, 1].nunique() <= 1:
        return 0.0
    value = frame.iloc[:, 0].corr(frame.iloc[:, 1], method=method)
    if value is None or math.isnan(float(value)) or math.isinf(float(value)):
        return 0.0
    return float(value)


def _sign_accuracy(x: pd.Series, y: pd.Series) -> float:
    frame = pd.concat([pd.to_numeric(x, errors="coerce"), pd.to_numeric(y, errors="coerce")], axis=1).replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) == 0:
        return 0.0
    pred = np.sign(frame.iloc[:, 0].to_numpy(dtype=float))
    actual = np.sign(frame.iloc[:, 1].to_numpy(dtype=float))
    mask = (pred != 0) & (actual != 0)
    if not np.any(mask):
        return 0.0
    return float((pred[mask] == actual[mask]).mean())
