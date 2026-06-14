from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import backtest_predictions, backtest_predictions_non_overlapping
from .config import AppConfig
from .data_schema import read_csv
from .features import build_features
from .labels import add_future_labels
from .models import evaluate_classification
from .pipeline import chronological_split

DEFAULT_RULE_SIGNALS = [
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
    "mid_ret_2r_bps",
    "mid_ret_5r_bps",
    "mid_ret_10r_bps",
    "mid_ret_20r_bps",
]


def evaluate_rule_baselines(
    *,
    book_path: str | Path,
    trades_path: str | Path | None,
    config_path: str | Path | None,
    out_dir: str | Path,
    signal_columns: list[str] | None = None,
    signal_thresholds: list[float] | None = None,
    clean: bool = False,
) -> dict[str, object]:
    """Evaluate deterministic signed-feature rules as sanity-check baselines."""
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    cfg = AppConfig.from_yaml(config_path)
    book = read_csv(book_path)
    trades = read_csv(trades_path) if trades_path else None
    features = build_features(book, trades=trades, cfg=cfg.features, timestamp_col=cfg.io.timestamp_col)
    dataset = add_future_labels(features, horizon_sec=cfg.labels.horizon_sec, threshold_bps=cfg.labels.threshold_bps)
    _, valid_df = chronological_split(dataset, cfg.split.train_ratio)

    candidates = signal_columns or DEFAULT_RULE_SIGNALS
    thresholds = signal_thresholds or [0.0, 0.05, 0.10, 0.20, 0.30, 0.50, 0.70]
    rows: list[dict[str, object]] = []
    meta_cols = ["timestamp", "mid", "future_mid", "future_return_bps", "label"]

    for col in candidates:
        if col not in valid_df.columns:
            continue
        score = robust_signed_score(valid_df[col])
        pred = valid_df[meta_cols].reset_index(drop=True).copy()
        pred["score"] = score
        pred["prob_edge"] = score
        pred["prob_up"] = np.clip((1.0 + score) / 2.0, 0.0, 1.0)
        pred["prob_down"] = np.clip((1.0 - score) / 2.0, 0.0, 1.0)
        pred["prob_flat"] = 0.0
        pred["pred_label"] = np.where(score > 0, 1, np.where(score < 0, -1, 0))
        cls = evaluate_classification(pred["label"], pred["pred_label"])
        for threshold in thresholds:
            _, event_bt = backtest_predictions(pred, cost_bps=cfg.backtest.cost_bps, edge_threshold=float(threshold))
            _, strict_bt = backtest_predictions_non_overlapping(
                pred,
                cost_bps=cfg.backtest.cost_bps,
                edge_threshold=float(threshold),
                horizon_sec=cfg.labels.horizon_sec,
            )
            row = {
                "signal": col,
                "signal_threshold": float(threshold),
                "accuracy": _f(cls.get("accuracy")),
                "balanced_accuracy": _f(cls.get("balanced_accuracy")),
                "macro_f1": _f(cls.get("macro_f1")),
                "event_trades": _f(event_bt.get("trades")),
                "event_hit_rate": _f(event_bt.get("hit_rate")),
                "event_mean_net_pnl_bps": _f(event_bt.get("mean_net_pnl_bps")),
                "event_total_net_pnl_bps": _f(event_bt.get("total_net_pnl_bps")),
                "strict_trades": _f(strict_bt.get("trades")),
                "strict_hit_rate": _f(strict_bt.get("hit_rate")),
                "strict_mean_net_pnl_bps": _f(strict_bt.get("mean_net_pnl_bps")),
                "strict_total_net_pnl_bps": _f(strict_bt.get("total_net_pnl_bps")),
            }
            row["rank_score"] = row["strict_mean_net_pnl_bps"] + 0.002 * row["strict_total_net_pnl_bps"] + 0.05 * row["balanced_accuracy"]
            rows.append(row)

    leaderboard = pd.DataFrame(rows)
    if not leaderboard.empty:
        leaderboard = leaderboard.sort_values(["rank_score", "strict_total_net_pnl_bps"], ascending=[False, False]).reset_index(drop=True)
        leaderboard.insert(0, "rank", range(1, len(leaderboard) + 1))
    leaderboard.to_csv(out / "rule_baselines.csv", index=False)
    result = {
        "book_path": str(book_path),
        "trades_path": str(trades_path) if trades_path else None,
        "rows_dataset": int(len(dataset)),
        "rows_valid": int(len(valid_df)),
        "rules_tested": int(leaderboard["signal"].nunique()) if not leaderboard.empty else 0,
        "rows_evaluated": int(len(leaderboard)),
        "best": leaderboard.head(1).to_dict(orient="records")[0] if not leaderboard.empty else None,
    }
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_rule_report(out / "REPORT.md", result, leaderboard)
    return result


def robust_signed_score(series: pd.Series) -> np.ndarray:
    x = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy(dtype=float)
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med)))
    scale = 1.4826 * mad if mad > 0 else float(np.std(x))
    if scale <= 1e-12:
        return np.zeros_like(x)
    return np.tanh((x - med) / scale)


def write_rule_report(path: str | Path, result: dict[str, object], leaderboard: pd.DataFrame) -> None:
    lines = [
        "# Rule Baseline Report",
        "",
        f"Book path: `{result.get('book_path')}`",
        f"Rows after label construction: {result.get('rows_dataset')}",
        f"Validation rows: {result.get('rows_valid')}",
        f"Rules tested: {result.get('rules_tested')}",
        "",
        "## Top rules",
        "",
    ]
    if leaderboard.empty:
        lines.append("No matching rule columns were found.")
    else:
        cols = [
            "rank",
            "signal",
            "signal_threshold",
            "balanced_accuracy",
            "macro_f1",
            "event_mean_net_pnl_bps",
            "event_total_net_pnl_bps",
            "strict_mean_net_pnl_bps",
            "strict_total_net_pnl_bps",
            "rank_score",
        ]
        lines.append(leaderboard[cols].head(30).to_markdown(index=False))
    lines.extend([
        "",
        "## Notes",
        "",
        "Rule baselines turn one signed feature into a direction signal. They are useful for detecting whether a model is learning more than the obvious microprice, imbalance, or OFI rule.",
        "",
    ])
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def _f(value: object) -> float:
    try:
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return 0.0
        return out
    except Exception:
        return 0.0


def run_rule_baselines(
    *,
    book_path: str | Path,
    trades_path: str | Path | None,
    config_path: str | Path | None,
    out_dir: str | Path,
    signal_thresholds: list[float] | None = None,
) -> dict[str, object]:
    """Compatibility wrapper used by the CLI."""
    return evaluate_rule_baselines(
        book_path=book_path,
        trades_path=trades_path,
        config_path=config_path,
        out_dir=out_dir,
        signal_thresholds=signal_thresholds,
        clean=False,
    )
