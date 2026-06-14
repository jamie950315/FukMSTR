from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import build_signals, summarize_trades
from .data_schema import timestamps_to_ns


@dataclass(frozen=True)
class StressGateConfig:
    min_trades: int = 20
    min_mean_net_bps: float = 0.0
    min_total_net_bps: float = 0.0
    min_bootstrap_mean_p05_bps: float = 0.0
    max_drawdown_floor_bps: float = -250.0
    require_all_cost_latency_positive: bool = False


def backtest_latency_non_overlapping(
    predictions: pd.DataFrame,
    *,
    cost_bps: float,
    edge_threshold: float,
    horizon_sec: float,
    latency_sec: float = 0.0,
    timestamp_col: str = "timestamp",
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Conservative non-overlap backtest with delayed entry.

    A signal is generated at timestamp t. The simulated entry price is the first observed mid at or after
    t + latency_sec, and the exit price is the precomputed future_mid at t + horizon_sec. This penalizes signals that
    only worked at the instantaneous quote. The function keeps at most one trade per horizon window.
    """
    required = {timestamp_col, "mid", "future_mid", "prob_up", "prob_down"}
    missing = required.difference(predictions.columns)
    if missing:
        raise ValueError(f"prediction frame missing columns: {sorted(missing)}")
    if latency_sec < 0:
        raise ValueError("latency_sec must be non-negative")

    out = predictions.copy().sort_values(timestamp_col).reset_index(drop=True)
    out["raw_signal"] = build_signals(out, edge_threshold=edge_threshold).to_numpy(dtype=int)
    ts_ns = timestamps_to_ns(out[timestamp_col])
    mid = out["mid"].astype(float).to_numpy()
    future_mid = out["future_mid"].astype(float).to_numpy()
    horizon_ns = int(float(horizon_sec) * 1_000_000_000)
    latency_ns = int(float(latency_sec) * 1_000_000_000)

    entry_target_ns = ts_ns + latency_ns
    entry_idx = np.searchsorted(ts_ns, entry_target_ns, side="left")
    valid_entry = entry_idx < len(out)
    entry_mid = np.full(len(out), np.nan, dtype=float)
    entry_mid[valid_entry] = mid[entry_idx[valid_entry]]

    signal = np.zeros(len(out), dtype=int)
    next_allowed = -np.inf
    for i, (sig, ts) in enumerate(zip(out["raw_signal"].to_numpy(dtype=int), ts_ns)):
        if sig == 0 or ts < next_allowed:
            continue
        if not valid_entry[i]:
            continue
        # Entry after or at the nominal exit horizon is not executable for this horizon.
        if entry_target_ns[i] >= ts + horizon_ns:
            continue
        if not np.isfinite(entry_mid[i]) or not np.isfinite(future_mid[i]) or entry_mid[i] <= 0:
            continue
        signal[i] = int(sig)
        next_allowed = int(ts) + horizon_ns

    out["signal"] = signal
    out["traded"] = (out["signal"] != 0).astype(int)
    out["entry_mid_latency"] = entry_mid
    out["latency_sec"] = float(latency_sec)
    out["gross_pnl_bps"] = out["signal"] * ((future_mid - entry_mid) / entry_mid * 10000.0)
    out.loc[out["traded"] == 0, "gross_pnl_bps"] = 0.0
    out["cost_bps"] = out["traded"] * float(cost_bps)
    out["net_pnl_bps"] = out["gross_pnl_bps"] - out["cost_bps"]
    out["equity_bps"] = out["net_pnl_bps"].cumsum()
    metrics = summarize_trades(out)
    metrics.update(
        {
            "mode": "latency_non_overlap",
            "edge_threshold": float(edge_threshold),
            "cost_bps": float(cost_bps),
            "horizon_sec": float(horizon_sec),
            "latency_sec": float(latency_sec),
        }
    )
    return out, metrics


def stress_sweep_predictions(
    predictions: pd.DataFrame,
    *,
    horizon_sec: float,
    cost_bps_values: list[float],
    latency_sec_values: list[float],
    edge_thresholds: list[float],
) -> pd.DataFrame:
    records: list[dict[str, float]] = []
    for cost in cost_bps_values:
        for latency in latency_sec_values:
            for edge in edge_thresholds:
                _, metrics = backtest_latency_non_overlapping(
                    predictions,
                    cost_bps=float(cost),
                    edge_threshold=float(edge),
                    horizon_sec=float(horizon_sec),
                    latency_sec=float(latency),
                )
                records.append(metrics)
    out = pd.DataFrame(records)
    if out.empty:
        return out
    out["robust_score"] = (
        out["mean_net_pnl_bps"].astype(float).clip(-5, 5)
        + 0.0015 * out["total_net_pnl_bps"].astype(float).clip(-1000, 1000)
        + 0.03 * out["hit_rate"].astype(float)
        - 0.002 * out["max_drawdown_bps"].astype(float).abs().clip(0, 1000)
    )
    return out.sort_values(["robust_score", "total_net_pnl_bps"], ascending=[False, False]).reset_index(drop=True)


def block_bootstrap_pnl(
    pnl: pd.Series | np.ndarray,
    *,
    iterations: int = 1000,
    block_size: int = 10,
    seed: int = 42,
) -> dict[str, float]:
    arr = np.asarray(pnl, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return {
            "trades": 0.0,
            "mean_p05_bps": 0.0,
            "mean_p50_bps": 0.0,
            "mean_p95_bps": 0.0,
            "total_p05_bps": 0.0,
            "total_p50_bps": 0.0,
            "total_p95_bps": 0.0,
            "prob_mean_gt_0": 0.0,
        }
    block_size = max(1, min(int(block_size), len(arr)))
    starts = np.arange(0, len(arr))
    rng = np.random.default_rng(seed)
    means = np.empty(iterations, dtype=float)
    totals = np.empty(iterations, dtype=float)
    for i in range(iterations):
        chunks: list[np.ndarray] = []
        while sum(len(x) for x in chunks) < len(arr):
            start = int(rng.choice(starts))
            end = min(len(arr), start + block_size)
            chunks.append(arr[start:end])
        sample = np.concatenate(chunks)[: len(arr)]
        means[i] = float(sample.mean())
        totals[i] = float(sample.sum())
    return {
        "trades": float(len(arr)),
        "mean_p05_bps": float(np.quantile(means, 0.05)),
        "mean_p50_bps": float(np.quantile(means, 0.50)),
        "mean_p95_bps": float(np.quantile(means, 0.95)),
        "total_p05_bps": float(np.quantile(totals, 0.05)),
        "total_p50_bps": float(np.quantile(totals, 0.50)),
        "total_p95_bps": float(np.quantile(totals, 0.95)),
        "prob_mean_gt_0": float((means > 0).mean()),
    }


def evaluate_profit_gate(
    predictions: pd.DataFrame,
    *,
    horizon_sec: float,
    edge_threshold: float,
    cost_bps: float,
    latency_sec: float,
    gate: StressGateConfig | None = None,
    bootstrap_iterations: int = 1000,
    bootstrap_block_size: int = 10,
) -> tuple[pd.DataFrame, dict[str, object]]:
    gate = gate or StressGateConfig()
    frame, metrics = backtest_latency_non_overlapping(
        predictions,
        cost_bps=cost_bps,
        edge_threshold=edge_threshold,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
    )
    trades = frame[frame["traded"] == 1]
    ci = block_bootstrap_pnl(
        trades["net_pnl_bps"],
        iterations=bootstrap_iterations,
        block_size=bootstrap_block_size,
    )
    checks = {
        "min_trades": metrics.get("trades", 0.0) >= gate.min_trades,
        "min_mean_net_bps": metrics.get("mean_net_pnl_bps", 0.0) > gate.min_mean_net_bps,
        "min_total_net_bps": metrics.get("total_net_pnl_bps", 0.0) > gate.min_total_net_bps,
        "bootstrap_mean_p05_positive": ci.get("mean_p05_bps", 0.0) > gate.min_bootstrap_mean_p05_bps,
        "max_drawdown_floor": metrics.get("max_drawdown_bps", 0.0) >= gate.max_drawdown_floor_bps,
    }
    passed = bool(all(checks.values()))
    result: dict[str, object] = {
        "passed": passed,
        "checks": checks,
        "metrics": metrics,
        "bootstrap": ci,
        "gate": gate.__dict__,
    }
    return frame, result


def regime_breakdown(
    predictions: pd.DataFrame,
    *,
    horizon_sec: float,
    cost_bps: float,
    edge_threshold: float,
    latency_sec: float = 0.0,
) -> pd.DataFrame:
    """Evaluate the same signal by simple regimes available in the predictions CSV."""
    frame, _ = backtest_latency_non_overlapping(
        predictions,
        cost_bps=cost_bps,
        edge_threshold=edge_threshold,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
    )
    enriched = frame.copy()
    prob_up = enriched["prob_up"].astype(float) if "prob_up" in enriched.columns else pd.Series(0.0, index=enriched.index)
    prob_down = enriched["prob_down"].astype(float) if "prob_down" in enriched.columns else pd.Series(0.0, index=enriched.index)
    enriched["abs_edge"] = (prob_up - prob_down).abs()
    if "prob_confidence" not in enriched.columns:
        enriched["prob_confidence"] = enriched[["prob_down", "prob_flat", "prob_up"]].max(axis=1)
    rows: list[dict[str, object]] = []
    for col in ["abs_edge", "prob_confidence", "spread_bps", "mid_vol_20r_bps", "imbalance_l3"]:
        if col not in enriched.columns:
            continue
        series = pd.to_numeric(enriched[col], errors="coerce")
        if series.notna().sum() < 30 or float(series.nunique()) < 3:
            continue
        try:
            bucket = pd.qcut(series.rank(method="first"), q=3, labels=["low", "mid", "high"])
        except Exception:
            continue
        for level in ["low", "mid", "high"]:
            subset = enriched[bucket == level].copy()
            metrics = summarize_trades(subset)
            rows.append({"regime_feature": col, "bucket": level, **metrics})
    return pd.DataFrame(rows)



def evaluate_robust_grid_gate(stress_sweep: pd.DataFrame, *, min_trades: int = 20) -> dict[str, object]:
    """Pass only when one edge threshold remains positive across every tested cost/latency cell."""
    if stress_sweep.empty:
        return {"passed": False, "reason": "empty stress sweep", "candidates": []}
    rows: list[dict[str, object]] = []
    for edge, g in stress_sweep.groupby("edge_threshold"):
        min_trades_seen = float(g["trades"].min()) if "trades" in g.columns else 0.0
        candidate = {
            "edge_threshold": float(edge),
            "cells": int(len(g)),
            "positive_mean_cells": int((g["mean_net_pnl_bps"] > 0).sum()),
            "positive_total_cells": int((g["total_net_pnl_bps"] > 0).sum()),
            "min_trades": min_trades_seen,
            "min_mean_net_pnl_bps": float(g["mean_net_pnl_bps"].min()),
            "median_mean_net_pnl_bps": float(g["mean_net_pnl_bps"].median()),
            "min_total_net_pnl_bps": float(g["total_net_pnl_bps"].min()),
            "worst_drawdown_bps": float(g["max_drawdown_bps"].min()),
        }
        candidate["passed"] = bool(
            candidate["positive_mean_cells"] == candidate["cells"]
            and candidate["positive_total_cells"] == candidate["cells"]
            and candidate["min_trades"] >= min_trades
        )
        rows.append(candidate)
    candidates = sorted(
        rows,
        key=lambda x: (bool(x["passed"]), float(x["min_mean_net_pnl_bps"]), float(x["min_total_net_pnl_bps"])),
        reverse=True,
    )
    return {
        "passed": bool(candidates and candidates[0].get("passed")),
        "min_trades_required": int(min_trades),
        "best_candidate": candidates[0] if candidates else None,
        "candidates": candidates,
    }

def run_stress_report(
    *,
    predictions_path: str | Path,
    out_dir: str | Path,
    horizon_sec: float,
    edge_thresholds: list[float],
    cost_bps_values: list[float],
    latency_sec_values: list[float],
    gate_edge_threshold: float | None = None,
    gate_cost_bps: float | None = None,
    gate_latency_sec: float | None = None,
    clean: bool = False,
) -> dict[str, object]:
    out = Path(out_dir)
    if clean and out.exists():
        import shutil

        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    predictions = pd.read_csv(predictions_path)
    sweep = stress_sweep_predictions(
        predictions,
        horizon_sec=horizon_sec,
        cost_bps_values=cost_bps_values,
        latency_sec_values=latency_sec_values,
        edge_thresholds=edge_thresholds,
    )
    sweep.to_csv(out / "stress_sweep.csv", index=False)
    best = sweep.head(1).to_dict(orient="records")[0] if not sweep.empty else {}
    robust_grid_gate = evaluate_robust_grid_gate(sweep, min_trades=20)
    (out / "robust_grid_gate.json").write_text(json.dumps(robust_grid_gate, indent=2), encoding="utf-8")

    gate_edge = float(gate_edge_threshold if gate_edge_threshold is not None else best.get("edge_threshold", 0.5))
    gate_cost = float(gate_cost_bps if gate_cost_bps is not None else best.get("cost_bps", cost_bps_values[0]))
    gate_latency = float(gate_latency_sec if gate_latency_sec is not None else best.get("latency_sec", latency_sec_values[0]))
    gate_frame, gate_result = evaluate_profit_gate(
        predictions,
        horizon_sec=horizon_sec,
        edge_threshold=gate_edge,
        cost_bps=gate_cost,
        latency_sec=gate_latency,
        bootstrap_iterations=1000,
        bootstrap_block_size=10,
    )
    gate_frame.to_csv(out / "profit_gate_backtest.csv", index=False)
    (out / "profit_gate.json").write_text(json.dumps(gate_result, indent=2), encoding="utf-8")

    regimes = regime_breakdown(
        predictions,
        horizon_sec=horizon_sec,
        cost_bps=gate_cost,
        edge_threshold=gate_edge,
        latency_sec=gate_latency,
    )
    regimes.to_csv(out / "regime_breakdown.csv", index=False)

    result: dict[str, object] = {
        "predictions_path": str(predictions_path),
        "horizon_sec": float(horizon_sec),
        "best_stress_row": best,
        "gate_result": gate_result,
        "robust_grid_gate": robust_grid_gate,
        "stress_rows": int(len(sweep)),
        "regime_rows": int(len(regimes)),
        "out_dir": str(out),
    }
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_stress_report(out / "REPORT.md", result, sweep, regimes)
    return result


def write_stress_report(path: str | Path, result: dict[str, object], sweep: pd.DataFrame, regimes: pd.DataFrame) -> None:
    gate = result.get("gate_result", {}) if isinstance(result.get("gate_result"), dict) else {}
    robust_grid_gate = result.get("robust_grid_gate", {}) if isinstance(result.get("robust_grid_gate"), dict) else {}
    lines = [
        "# V04 Stress / Profit Gate Report",
        "",
        f"Predictions: `{result.get('predictions_path')}`",
        f"Horizon seconds: {result.get('horizon_sec')}",
        "",
        "## Best stress rows",
        "",
    ]
    if sweep.empty:
        lines.append("No stress rows generated.")
    else:
        cols = [
            "cost_bps",
            "latency_sec",
            "edge_threshold",
            "trades",
            "hit_rate",
            "mean_net_pnl_bps",
            "total_net_pnl_bps",
            "max_drawdown_bps",
            "robust_score",
        ]
        lines.append(sweep[cols].head(20).to_markdown(index=False))
    lines.extend(["", "## Robust grid gate", "", "```json", json.dumps(robust_grid_gate, indent=2), "```", ""])
    lines.extend(["", "## Point profit gate", "", "```json", json.dumps(gate, indent=2), "```", ""])
    if not regimes.empty:
        cols = ["regime_feature", "bucket", "trades", "hit_rate", "mean_net_pnl_bps", "total_net_pnl_bps", "max_drawdown_bps"]
        lines.extend(["## Regime breakdown", "", regimes[cols].to_markdown(index=False), ""])
    lines.extend(
        [
            "## Interpretation notes",
            "",
            "The pass/fail gate is intentionally conservative. A result that fails the gate may still contain short-horizon signal, but it has not cleared the minimum stability bar for research promotion.",
            "",
        ]
    )
    Path(path).write_text("\n".join(lines), encoding="utf-8")
