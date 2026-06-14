from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .ensemble import run_ensemble_walk_forward


@dataclass(frozen=True)
class LongWindowGateConfig:
    """Promotion thresholds for long-horizon research candidates.

    Long windows naturally produce fewer non-overlapping trades than 1s to 10s tests.
    This gate is stricter on profitability/stress, but uses an explicit trade-count floor
    that can be tuned separately from the v05 hard-coded per-fold 20-trade rule.
    """

    min_fold_trades: int = 10
    min_oof_trades: int = 30
    min_fold_mean_net_bps: float = 0.0
    min_fold_bootstrap_p05_bps: float = 0.0
    min_oof_mean_net_bps: float = 0.0
    min_oof_hit_rate: float = 0.55
    require_robust_gate: bool = True
    min_robust_mean_net_bps: float = 0.0
    min_robust_total_net_bps: float = 0.0


def parse_model_sets(raw: str | Iterable[str]) -> list[list[str]]:
    """Parse model grids like 'logistic;logistic,hgb;logistic,hgb,et'."""
    if isinstance(raw, str):
        chunks = [part.strip() for part in raw.split(";")]
    else:
        chunks = [str(part).strip() for part in raw]
    out: list[list[str]] = []
    for chunk in chunks:
        if not chunk:
            continue
        models = [m.strip() for m in chunk.split(",") if m.strip()]
        if models:
            out.append(models)
    if not out:
        raise ValueError("at least one model set is required")
    return out


def gate_long_window_candidate(
    *,
    fold_metrics: pd.DataFrame,
    stress_sweep: pd.DataFrame | None,
    summary: dict[str, object] | None = None,
    cfg: LongWindowGateConfig | None = None,
) -> dict[str, object]:
    """Apply the v06 long-window research gate to one completed run."""
    cfg = cfg or LongWindowGateConfig()
    summary = summary or {}
    aggregate = summary.get("aggregate") if isinstance(summary.get("aggregate"), dict) else {}
    profit_gate = summary.get("profit_gate") if isinstance(summary.get("profit_gate"), dict) else {}
    best_candidate = profit_gate.get("best_candidate") if isinstance(profit_gate.get("best_candidate"), dict) else {}

    failures: list[str] = []
    if fold_metrics.empty:
        failures.append("empty_fold_metrics")

    fold_trades_min = _min_col(fold_metrics, "valid_trades")
    fold_mean_net_min = _min_col(fold_metrics, "valid_mean_net_pnl_bps")
    fold_bootstrap_p05_min = _min_col(fold_metrics, "bootstrap_mean_p05_bps")
    fold_count = int(len(fold_metrics))
    positive_folds = int((pd.to_numeric(fold_metrics.get("valid_mean_net_pnl_bps", pd.Series(dtype=float)), errors="coerce") > 0).sum())

    oof_trades = _as_float(aggregate.get("oof_trades"))
    oof_mean = _as_float(aggregate.get("oof_mean_net_pnl_bps"))
    oof_total = _as_float(aggregate.get("oof_total_net_pnl_bps"))
    oof_hit = _as_float(aggregate.get("oof_hit_rate"))

    if fold_trades_min < cfg.min_fold_trades:
        failures.append("fold_trade_count_below_floor")
    if oof_trades < cfg.min_oof_trades:
        failures.append("oof_trade_count_below_floor")
    if fold_mean_net_min <= cfg.min_fold_mean_net_bps:
        failures.append("fold_mean_net_not_positive_enough")
    if fold_bootstrap_p05_min <= cfg.min_fold_bootstrap_p05_bps:
        failures.append("fold_bootstrap_lower_bound_not_positive")
    if oof_mean <= cfg.min_oof_mean_net_bps:
        failures.append("oof_mean_net_not_positive_enough")
    if oof_hit < cfg.min_oof_hit_rate:
        failures.append("oof_hit_rate_below_floor")
    if positive_folds < fold_count:
        failures.append("not_all_folds_positive")

    robust_passed = bool(profit_gate.get("passed"))
    robust_min_mean = _as_float(best_candidate.get("min_mean_net_pnl_bps"))
    robust_min_total = _as_float(best_candidate.get("min_total_net_pnl_bps"))
    if cfg.require_robust_gate and not robust_passed:
        failures.append("robust_profit_gate_failed")
    if np.isfinite(robust_min_mean) and robust_min_mean <= cfg.min_robust_mean_net_bps:
        failures.append("robust_min_mean_not_positive_enough")
    if np.isfinite(robust_min_total) and robust_min_total <= cfg.min_robust_total_net_bps:
        failures.append("robust_min_total_not_positive_enough")

    stress_rows = int(len(stress_sweep)) if stress_sweep is not None else 0
    stress_positive_cells = 0
    if stress_sweep is not None and not stress_sweep.empty and "mean_net_pnl_bps" in stress_sweep.columns:
        stress_positive_cells = int((pd.to_numeric(stress_sweep["mean_net_pnl_bps"], errors="coerce") > 0).sum())

    passed = not failures
    score = _rank_score(
        oof_mean=oof_mean,
        oof_total=oof_total,
        fold_mean_min=fold_mean_net_min,
        boot_min=fold_bootstrap_p05_min,
        trades=oof_trades,
        robust_min_mean=robust_min_mean,
    )
    return {
        "v06_long_window_pass": bool(passed),
        "failures": failures,
        "rank_score_v06": float(score),
        "gate_config": asdict(cfg),
        "fold_count": fold_count,
        "positive_folds": positive_folds,
        "fold_trades_min": float(fold_trades_min),
        "fold_mean_net_pnl_bps_min": float(fold_mean_net_min),
        "fold_bootstrap_p05_bps_min": float(fold_bootstrap_p05_min),
        "oof_trades": float(oof_trades),
        "oof_mean_net_pnl_bps": float(oof_mean),
        "oof_total_net_pnl_bps": float(oof_total),
        "oof_hit_rate": float(oof_hit),
        "robust_profit_gate_passed": robust_passed,
        "robust_min_mean_net_pnl_bps": float(robust_min_mean),
        "robust_min_total_net_pnl_bps": float(robust_min_total),
        "stress_rows": stress_rows,
        "stress_positive_mean_cells": stress_positive_cells,
    }


def summarize_completed_long_runs(
    run_dirs: Iterable[str | Path],
    *,
    gate_config: LongWindowGateConfig | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for run_dir in run_dirs:
        path = Path(run_dir)
        summary_path = path / "summary.json"
        fold_path = path / "fold_metrics.csv"
        stress_path = path / "oof_taker_stress_sweep.csv"
        if not summary_path.exists() or not fold_path.exists():
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        folds = pd.read_csv(fold_path)
        stress = pd.read_csv(stress_path) if stress_path.exists() else pd.DataFrame()
        gate = gate_long_window_candidate(fold_metrics=folds, stress_sweep=stress, summary=summary, cfg=gate_config)
        aggregate = summary.get("aggregate") if isinstance(summary.get("aggregate"), dict) else {}
        rows.append(
            {
                "run_dir": str(path),
                "horizon_sec": summary.get("horizon_sec"),
                "models": ",".join(summary.get("models", [])) if isinstance(summary.get("models"), list) else summary.get("models"),
                "top_k_features": summary.get("top_k_features"),
                "stationary_only": summary.get("stationary_only"),
                "threshold_bps": summary.get("threshold_bps"),
                "cost_bps": summary.get("cost_bps"),
                "latency_sec": summary.get("latency_sec"),
                "strict_research_pass_v05": aggregate.get("strict_research_pass") if isinstance(aggregate, dict) else None,
                **gate,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(
        ["v06_long_window_pass", "rank_score_v06", "oof_total_net_pnl_bps"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def run_long_horizon_sweep(
    *,
    book_path: str | Path,
    trades_path: str | Path | None,
    base_config_path: str | Path | None,
    out_dir: str | Path,
    horizons_sec: list[float],
    threshold_bps_values: list[float],
    model_sets: list[list[str]],
    top_k_features_values: list[int],
    candidate_edges: list[float],
    cost_bps: float,
    latency_sec: float,
    stress_cost_bps_values: list[float],
    stress_latency_sec_values: list[float],
    folds: int,
    min_train_ratio: float,
    valid_ratio: float,
    calibration_ratio: float,
    min_calibration_trades: int,
    stationary_only: bool = False,
    gate_config: LongWindowGateConfig | None = None,
    clean: bool = False,
    skip_existing: bool = True,
) -> dict[str, object]:
    """Run a reproducible grid for 30s+ horizons and produce a v06 leaderboard."""
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    run_dirs: list[Path] = []
    errors: list[dict[str, object]] = []
    for horizon in horizons_sec:
        for threshold_bps in threshold_bps_values:
            for top_k in top_k_features_values:
                for models in model_sets:
                    model_tag = "-".join(models)
                    run_name = f"h{_num_tag(horizon)}_thr{_num_tag(threshold_bps)}_top{top_k}_{model_tag}"
                    run_dir = out / run_name
                    run_dirs.append(run_dir)
                    if skip_existing and (run_dir / "summary.json").exists():
                        continue
                    try:
                        run_ensemble_walk_forward(
                            book_path=book_path,
                            trades_path=trades_path,
                            base_config_path=base_config_path,
                            out_dir=run_dir,
                            horizon_sec=float(horizon),
                            threshold_bps=float(threshold_bps),
                            model_types=models,
                            candidate_edges=candidate_edges,
                            cost_bps=float(cost_bps),
                            latency_sec=float(latency_sec),
                            stress_cost_bps_values=stress_cost_bps_values,
                            stress_latency_sec_values=stress_latency_sec_values,
                            folds=int(folds),
                            min_train_ratio=float(min_train_ratio),
                            valid_ratio=float(valid_ratio),
                            calibration_ratio=float(calibration_ratio),
                            top_k_features=int(top_k),
                            min_calibration_trades=int(min_calibration_trades),
                            stationary_only=bool(stationary_only),
                            clean=True,
                        )
                    except Exception as exc:  # pragma: no cover - errors are reported as artifacts.
                        errors.append({"run_dir": str(run_dir), "error": repr(exc)})
                        run_dir.mkdir(parents=True, exist_ok=True)
                        (run_dir / "ERROR.txt").write_text(repr(exc), encoding="utf-8")

    leaderboard = summarize_completed_long_runs(run_dirs, gate_config=gate_config)
    leaderboard_path = out / "long_horizon_leaderboard.csv"
    leaderboard.to_csv(leaderboard_path, index=False)
    result = {
        "book_path": str(book_path),
        "trades_path": str(trades_path) if trades_path else None,
        "horizons_sec": [float(x) for x in horizons_sec],
        "threshold_bps_values": [float(x) for x in threshold_bps_values],
        "model_sets": model_sets,
        "top_k_features_values": [int(x) for x in top_k_features_values],
        "stationary_only": bool(stationary_only),
        "candidate_edges": [float(x) for x in candidate_edges],
        "cost_bps": float(cost_bps),
        "latency_sec": float(latency_sec),
        "stress_cost_bps_values": [float(x) for x in stress_cost_bps_values],
        "stress_latency_sec_values": [float(x) for x in stress_latency_sec_values],
        "gate_config": asdict(gate_config or LongWindowGateConfig()),
        "completed_runs": int(len(leaderboard)),
        "errors": errors,
        "leaderboard_path": str(leaderboard_path),
        "best": leaderboard.head(1).to_dict(orient="records") if not leaderboard.empty else [],
    }
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_long_horizon_report(out / "REPORT.md", result, leaderboard)
    return result


def write_long_horizon_report(path: str | Path, result: dict[str, object], leaderboard: pd.DataFrame) -> None:
    lines = [
        "# Long Horizon Sweep Report",
        "",
        "This report ranks 30s+ taker bid/ask non-overlap experiments using the v06 long-window research gate.",
        "",
        "## Grid",
        "",
        f"- horizons_sec: {result.get('horizons_sec')}",
        f"- threshold_bps_values: {result.get('threshold_bps_values')}",
        f"- model_sets: {result.get('model_sets')}",
        f"- top_k_features_values: {result.get('top_k_features_values')}",
        f"- candidate_edges: {result.get('candidate_edges')}",
        f"- cost_bps: {result.get('cost_bps')}",
        f"- latency_sec: {result.get('latency_sec')}",
        f"- stress_cost_bps_values: {result.get('stress_cost_bps_values')}",
        f"- stress_latency_sec_values: {result.get('stress_latency_sec_values')}",
        "",
        "## Gate config",
        "",
        "```json",
        json.dumps(result.get("gate_config", {}), indent=2),
        "```",
        "",
    ]
    if leaderboard.empty:
        lines.extend(["No completed runs were summarized.", ""])
    else:
        show_cols = [
            "run_dir",
            "horizon_sec",
            "models",
            "top_k_features",
            "stationary_only",
            "v06_long_window_pass",
            "rank_score_v06",
            "fold_trades_min",
            "oof_trades",
            "oof_mean_net_pnl_bps",
            "oof_total_net_pnl_bps",
            "fold_bootstrap_p05_bps_min",
            "robust_min_mean_net_pnl_bps",
        ]
        show_cols = [c for c in show_cols if c in leaderboard.columns]
        lines.extend(["## Leaderboard", "", leaderboard[show_cols].head(20).to_markdown(index=False), ""])
    if result.get("errors"):
        lines.extend(["## Errors", "", "```json", json.dumps(result.get("errors"), indent=2), "```", ""])
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def _rank_score(*, oof_mean: float, oof_total: float, fold_mean_min: float, boot_min: float, trades: float, robust_min_mean: float) -> float:
    parts = [
        1.0 * np.clip(oof_mean, -20.0, 20.0),
        0.25 * np.clip(fold_mean_min, -20.0, 20.0),
        0.25 * np.clip(boot_min, -20.0, 20.0),
        0.10 * np.clip(robust_min_mean, -20.0, 20.0),
        0.002 * np.clip(oof_total, -2000.0, 2000.0),
        0.01 * min(max(trades, 0.0), 200.0),
    ]
    return float(np.nansum(parts))


def _min_col(frame: pd.DataFrame, col: str) -> float:
    if col not in frame.columns or frame.empty:
        return float("nan")
    vals = pd.to_numeric(frame[col], errors="coerce")
    return float(vals.min()) if vals.notna().any() else float("nan")


def _as_float(value: object) -> float:
    try:
        return float(value)
    except Exception:
        return float("nan")


def _num_tag(value: float) -> str:
    return str(value).replace(".", "p").replace("-", "m")
