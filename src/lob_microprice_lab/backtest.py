from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .data_schema import timestamps_to_ns


def build_signals(predictions: pd.DataFrame, edge_threshold: float) -> pd.Series:
    p_up = predictions.get("prob_up", pd.Series(0.0, index=predictions.index)).astype(float)
    p_down = predictions.get("prob_down", pd.Series(0.0, index=predictions.index)).astype(float)
    edge = p_up - p_down
    signal = np.where(edge >= edge_threshold, 1, np.where(edge <= -edge_threshold, -1, 0))
    return pd.Series(signal, index=predictions.index, name="signal")


def backtest_predictions(predictions: pd.DataFrame, cost_bps: float, edge_threshold: float) -> tuple[pd.DataFrame, dict[str, float]]:
    """Event-level backtest for model triage.

    Every non-zero signal is counted as a trade. For overlapping horizon labels, this intentionally overstates the number
    of executable independent opportunities. Use `backtest_predictions_non_overlapping` for a stricter sanity check.
    """
    required = {"future_return_bps"}
    missing = required.difference(predictions.columns)
    if missing:
        raise ValueError(f"prediction frame missing columns: {sorted(missing)}")

    out = predictions.copy()
    out["signal"] = build_signals(out, edge_threshold=edge_threshold)
    out["traded"] = (out["signal"] != 0).astype(int)
    out["gross_pnl_bps"] = out["signal"] * out["future_return_bps"].astype(float)
    out["cost_bps"] = out["traded"] * float(cost_bps)
    out["net_pnl_bps"] = out["gross_pnl_bps"] - out["cost_bps"]
    out["equity_bps"] = out["net_pnl_bps"].cumsum()
    metrics = summarize_trades(out)
    metrics["mode"] = "event"
    metrics["edge_threshold"] = float(edge_threshold)
    metrics["cost_bps"] = float(cost_bps)
    return out, metrics


def backtest_predictions_non_overlapping(
    predictions: pd.DataFrame,
    cost_bps: float,
    edge_threshold: float,
    horizon_sec: float,
    timestamp_col: str = "timestamp",
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Take at most one position for each horizon window.

    This is still a simplified research backtest, but it removes the largest artifact in overlapping event-level labels:
    counting many half-second predictions against the same ten-second future move.
    """
    required = {"future_return_bps", timestamp_col}
    missing = required.difference(predictions.columns)
    if missing:
        raise ValueError(f"prediction frame missing columns: {sorted(missing)}")

    out = predictions.copy().sort_values(timestamp_col).reset_index(drop=True)
    raw_signal = build_signals(out, edge_threshold=edge_threshold).to_numpy(dtype=int)
    ts_ns = timestamps_to_ns(out[timestamp_col])
    horizon_ns = int(float(horizon_sec) * 1_000_000_000)
    kept = np.zeros(len(out), dtype=int)
    next_allowed = -np.inf
    for i, (sig, ts) in enumerate(zip(raw_signal, ts_ns)):
        if sig == 0 or ts < next_allowed:
            continue
        kept[i] = int(sig)
        next_allowed = int(ts) + horizon_ns

    out["signal"] = kept
    out["traded"] = (out["signal"] != 0).astype(int)
    out["gross_pnl_bps"] = out["signal"] * out["future_return_bps"].astype(float)
    out["cost_bps"] = out["traded"] * float(cost_bps)
    out["net_pnl_bps"] = out["gross_pnl_bps"] - out["cost_bps"]
    out["equity_bps"] = out["net_pnl_bps"].cumsum()
    metrics = summarize_trades(out)
    metrics["mode"] = "non_overlap"
    metrics["edge_threshold"] = float(edge_threshold)
    metrics["cost_bps"] = float(cost_bps)
    metrics["horizon_sec"] = float(horizon_sec)
    return out, metrics


def summarize_trades(frame: pd.DataFrame) -> dict[str, float]:
    trades = frame[frame["traded"] == 1]
    base = {
        "events": float(len(frame)),
        "trades": float(len(trades)),
        "trade_rate": float(len(trades) / len(frame)) if len(frame) else 0.0,
    }
    if trades.empty:
        return {
            **base,
            "hit_rate": 0.0,
            "mean_net_pnl_bps": 0.0,
            "median_net_pnl_bps": 0.0,
            "total_net_pnl_bps": 0.0,
            "sharpe_like": 0.0,
            "max_drawdown_bps": 0.0,
            "profit_factor": 0.0,
        }

    pnl = trades["net_pnl_bps"].astype(float)
    std = float(pnl.std(ddof=1)) if len(pnl) > 1 else 0.0
    equity = trades["net_pnl_bps"].astype(float).cumsum()
    peak = equity.cummax()
    drawdown = equity - peak
    gross_profit = float(pnl[pnl > 0].sum())
    gross_loss = float(-pnl[pnl < 0].sum())
    return {
        **base,
        "hit_rate": float((pnl > 0).mean()),
        "mean_net_pnl_bps": float(pnl.mean()),
        "median_net_pnl_bps": float(pnl.median()),
        "total_net_pnl_bps": float(pnl.sum()),
        "sharpe_like": float(pnl.mean() / std * np.sqrt(len(pnl))) if std > 0 else 0.0,
        "max_drawdown_bps": float(drawdown.min()) if len(drawdown) else 0.0,
        "profit_factor": float(gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0),
    }


def sweep_edge_thresholds(
    predictions: pd.DataFrame,
    cost_bps: float,
    thresholds: list[float],
    horizon_sec: float | None = None,
) -> pd.DataFrame:
    records: list[dict[str, float]] = []
    for threshold in thresholds:
        _, event_metrics = backtest_predictions(predictions, cost_bps=cost_bps, edge_threshold=float(threshold))
        records.append({"edge_threshold": float(threshold), **event_metrics})
        if horizon_sec is not None:
            _, strict_metrics = backtest_predictions_non_overlapping(
                predictions,
                cost_bps=cost_bps,
                edge_threshold=float(threshold),
                horizon_sec=float(horizon_sec),
            )
            records.append({"edge_threshold": float(threshold), **strict_metrics})
    out = pd.DataFrame(records)
    if not out.empty:
        out["rank_score"] = (
            out["mean_net_pnl_bps"].astype(float).clip(-5, 5)
            + 0.002 * out["total_net_pnl_bps"].astype(float).clip(-500, 500)
            + 0.05 * out["hit_rate"].astype(float)
        )
        out = out.sort_values(["mode", "rank_score", "total_net_pnl_bps"], ascending=[True, False, False]).reset_index(drop=True)
    return out


def save_backtest_report(metrics: dict[str, float], path: str | Path) -> None:
    Path(path).write_text(json.dumps(metrics, indent=2), encoding="utf-8")
