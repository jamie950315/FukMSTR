from __future__ import annotations

import json
import math
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from .backtest import backtest_predictions, save_backtest_report
from .config import AppConfig
from .data_schema import read_csv
from .features import build_features
from .labels import add_future_labels
from .models import evaluate_classification, predict_frame, save_model_artifacts, select_feature_columns, train_model
from .pipeline import _label_distribution, chronological_split


@dataclass(frozen=True)
class TuneTrial:
    horizon_sec: float
    threshold_bps: float
    model_type: str
    edge_threshold: float


def parse_float_list(raw: str | Iterable[float]) -> list[float]:
    if isinstance(raw, str):
        values = [x.strip() for x in raw.split(",") if x.strip()]
        if not values:
            raise ValueError("empty float list")
        return [float(x) for x in values]
    return [float(x) for x in raw]


def parse_str_list(raw: str | Iterable[str]) -> list[str]:
    if isinstance(raw, str):
        values = [x.strip() for x in raw.split(",") if x.strip()]
        if not values:
            raise ValueError("empty string list")
        return values
    return [str(x) for x in raw]


def build_trials(
    horizons_sec: Iterable[float],
    thresholds_bps: Iterable[float],
    models: Iterable[str],
    edge_thresholds: Iterable[float],
) -> list[TuneTrial]:
    return [
        TuneTrial(float(h), float(t), str(m), float(e))
        for h in horizons_sec
        for t in thresholds_bps
        for m in models
        for e in edge_thresholds
    ]


def run_tuning(
    *,
    book_path: str | Path,
    trades_path: str | Path | None,
    base_config_path: str | Path | None,
    out_dir: str | Path,
    horizons_sec: Iterable[float],
    thresholds_bps: Iterable[float],
    models: Iterable[str],
    edge_thresholds: Iterable[float],
    clean: bool = False,
) -> dict[str, object]:
    """Run a chronological grid search over horizons, label thresholds, models, and signal thresholds."""
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    runs_dir = out / "runs"
    runs_dir.mkdir(exist_ok=True)

    base_cfg = AppConfig.from_yaml(base_config_path)
    book = read_csv(book_path)
    trades = read_csv(trades_path) if trades_path else None
    features = build_features(book, trades=trades, cfg=base_cfg.features, timestamp_col=base_cfg.io.timestamp_col)

    trials = build_trials(horizons_sec, thresholds_bps, models, edge_thresholds)
    records: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []

    for idx, trial in enumerate(trials, start=1):
        cfg = AppConfig.from_yaml(base_config_path)
        cfg.labels.horizon_sec = trial.horizon_sec
        cfg.labels.threshold_bps = trial.threshold_bps
        cfg.model.type = trial.model_type
        cfg.backtest.signal_edge_threshold = trial.edge_threshold

        run_name = _trial_name(idx, trial)
        run_dir = runs_dir / run_name
        cfg_path = run_dir / "config.yaml"
        run_dir.mkdir(parents=True, exist_ok=True)
        cfg.to_yaml(cfg_path)
        try:
            summary = _run_trial_from_features(features, cfg, run_dir)
            record = _summary_record(idx, trial, run_dir, summary)
            records.append(record)
        except Exception as exc:  # keep a full grid from stopping on one bad label split
            failures.append({"trial_index": idx, "trial": asdict(trial), "error": repr(exc), "run_dir": str(run_dir)})

    leaderboard = pd.DataFrame(records)
    if not leaderboard.empty:
        leaderboard = leaderboard.sort_values(
            ["rank_score", "balanced_accuracy", "macro_f1", "mean_net_pnl_bps"],
            ascending=[False, False, False, False],
        ).reset_index(drop=True)
        leaderboard.insert(0, "rank", range(1, len(leaderboard) + 1))
    leaderboard_path = out / "leaderboard.csv"
    leaderboard.to_csv(leaderboard_path, index=False)

    best = leaderboard.iloc[0].to_dict() if not leaderboard.empty else None
    result = {
        "book_path": str(book_path),
        "trades_path": str(trades_path) if trades_path else None,
        "rows_features": int(len(features)),
        "trials_requested": len(trials),
        "trials_completed": len(records),
        "trials_failed": len(failures),
        "leaderboard_path": str(leaderboard_path),
        "best": best,
        "failures": failures,
    }
    (out / "tuning_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_markdown_report(out / "REPORT.md", result, leaderboard)
    return result


def _run_trial_from_features(features: pd.DataFrame, cfg: AppConfig, out_dir: str | Path) -> dict[str, object]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dataset = add_future_labels(features, horizon_sec=cfg.labels.horizon_sec, threshold_bps=cfg.labels.threshold_bps)
    if len(dataset) < 100:
        raise ValueError(f"dataset too small after feature/label construction: {len(dataset)} rows")

    train_df, valid_df = chronological_split(dataset, cfg.split.train_ratio)
    feature_columns = select_feature_columns(dataset)
    X_train = train_df[feature_columns]
    y_train = train_df["label"]
    X_valid = valid_df[feature_columns]
    y_valid = valid_df["label"]

    model = train_model(X_train, y_train, cfg.model)
    meta_cols = ["timestamp", "mid", "future_mid", "future_return_bps", "label"]
    pred_valid = predict_frame(model, X_valid, valid_df[meta_cols])

    metrics = evaluate_classification(y_valid, pred_valid["pred_label"])
    bt_frame, bt_metrics = backtest_predictions(
        pred_valid,
        cost_bps=cfg.backtest.cost_bps,
        edge_threshold=cfg.backtest.signal_edge_threshold,
    )

    save_model_artifacts(model, feature_columns, out)
    cfg.to_yaml(out / "config_resolved.yaml")
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    save_backtest_report(bt_metrics, out / "backtest.json")
    pred_valid.to_csv(out / "predictions_valid.csv", index=False)
    bt_frame.to_csv(out / "backtest_valid.csv", index=False)

    summary = {
        "rows_total": int(len(dataset)),
        "rows_train": int(len(train_df)),
        "rows_valid": int(len(valid_df)),
        "feature_count": int(len(feature_columns)),
        "label_distribution_train": _label_distribution(y_train),
        "label_distribution_valid": _label_distribution(y_valid),
        "metrics": metrics,
        "backtest": bt_metrics,
        "out_dir": str(out),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def write_markdown_report(path: str | Path, result: dict[str, object], leaderboard: pd.DataFrame) -> None:
    lines = [
        "# Real Data Tuning Report",
        "",
        f"Book path: `{result.get('book_path')}`",
        f"Trades path: `{result.get('trades_path')}`",
        f"Rows after feature construction: {result.get('rows_features')}",
        f"Trials requested: {result.get('trials_requested')}",
        f"Trials completed: {result.get('trials_completed')}",
        f"Trials failed: {result.get('trials_failed')}",
        "",
    ]
    if leaderboard.empty:
        lines.extend(["No successful trials.", ""])
    else:
        display_cols = [
            "rank",
            "horizon_sec",
            "threshold_bps",
            "model_type",
            "edge_threshold",
            "accuracy",
            "balanced_accuracy",
            "macro_f1",
            "majority_accuracy_valid",
            "accuracy_lift_vs_majority",
            "trades",
            "mean_net_pnl_bps",
            "rank_score",
        ]
        lines.extend([
            "## Top trials",
            "",
            leaderboard[display_cols].head(10).to_markdown(index=False),
            "",
            "## Metric notes",
            "",
            "`balanced_accuracy` is more useful than raw accuracy when the flat class dominates.",
            "`rank_score` rewards balanced accuracy above a majority-class baseline, macro-F1, and positive mean net PnL after the configured event cost.",
            "The included backtest is event-level triage; it does not model queue position, partial fills, latency, or exchange matching behavior.",
            "",
        ])
    if result.get("failures"):
        lines.extend(["## Failed trials", "", "```json", json.dumps(result["failures"], indent=2), "```", ""])
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def _summary_record(idx: int, trial: TuneTrial, run_dir: Path, summary: dict[str, object]) -> dict[str, object]:
    metrics = summary.get("metrics", {}) if isinstance(summary.get("metrics"), dict) else {}
    backtest = summary.get("backtest", {}) if isinstance(summary.get("backtest"), dict) else {}
    label_train = summary.get("label_distribution_train", {}) if isinstance(summary.get("label_distribution_train"), dict) else {}
    label_valid = summary.get("label_distribution_valid", {}) if isinstance(summary.get("label_distribution_valid"), dict) else {}

    valid_total = sum(int(v) for v in label_valid.values()) or 1
    majority_valid = max((int(v) for v in label_valid.values()), default=0) / valid_total
    balanced_accuracy = _float(metrics.get("balanced_accuracy"))
    macro_f1 = _float(metrics.get("macro_f1"))
    mean_net = _float(backtest.get("mean_net_pnl_bps"))
    rank_score = (balanced_accuracy - 1.0 / 3.0) + 0.25 * macro_f1 + 0.02 * max(min(mean_net, 5.0), -5.0)

    return {
        "trial_index": idx,
        "horizon_sec": trial.horizon_sec,
        "threshold_bps": trial.threshold_bps,
        "model_type": trial.model_type,
        "edge_threshold": trial.edge_threshold,
        "rows_total": summary.get("rows_total"),
        "rows_train": summary.get("rows_train"),
        "rows_valid": summary.get("rows_valid"),
        "feature_count": summary.get("feature_count"),
        "accuracy": _float(metrics.get("accuracy")),
        "balanced_accuracy": balanced_accuracy,
        "macro_f1": macro_f1,
        "majority_accuracy_valid": majority_valid,
        "accuracy_lift_vs_majority": _float(metrics.get("accuracy")) - majority_valid,
        "trades": _float(backtest.get("trades")),
        "trade_rate": _float(backtest.get("trade_rate")),
        "hit_rate": _float(backtest.get("hit_rate")),
        "mean_net_pnl_bps": mean_net,
        "total_net_pnl_bps": _float(backtest.get("total_net_pnl_bps")),
        "sharpe_like": _float(backtest.get("sharpe_like")),
        "rank_score": rank_score,
        "label_distribution_train": json.dumps(label_train, sort_keys=True),
        "label_distribution_valid": json.dumps(label_valid, sort_keys=True),
        "run_dir": str(run_dir),
    }


def _float(value: object) -> float:
    try:
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return 0.0
        return out
    except Exception:
        return 0.0


def _trial_name(idx: int, trial: TuneTrial) -> str:
    return (
        f"trial_{idx:03d}_h{_num_key(trial.horizon_sec)}_thr{_num_key(trial.threshold_bps)}_"
        f"{trial.model_type}_edge{_num_key(trial.edge_threshold)}"
    )


def _num_key(value: float) -> str:
    return str(value).replace(".", "p").replace("-", "m")
