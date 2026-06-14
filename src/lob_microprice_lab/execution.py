from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import build_signals, summarize_trades
from .data_schema import timestamps_to_ns


def backtest_taker_bidask_non_overlapping(
    predictions: pd.DataFrame,
    *,
    cost_bps: float,
    edge_threshold: float,
    horizon_sec: float,
    latency_sec: float = 0.0,
    timestamp_col: str = "timestamp",
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Conservative taker-style non-overlap execution simulation.

    Long signal: buy at future best ask after latency, sell at best bid near horizon.
    Short signal: sell at future best bid after latency, buy at best ask near horizon.

    This intentionally penalizes spread crossing twice. It is still a research simulator: it does not model exchange
    matching, queue position, partial fills, funding, liquidation mechanics, or market impact.
    """
    required = {timestamp_col, "best_bid", "best_ask", "prob_up", "prob_down"}
    missing = required.difference(predictions.columns)
    if missing:
        raise ValueError(f"prediction frame missing columns for bid/ask execution: {sorted(missing)}")
    if latency_sec < 0:
        raise ValueError("latency_sec must be non-negative")

    out = predictions.copy().sort_values(timestamp_col).reset_index(drop=True)
    out["raw_signal"] = build_signals(out, edge_threshold=edge_threshold).to_numpy(dtype=int)
    ts_ns = timestamps_to_ns(out[timestamp_col])
    bid = out["best_bid"].astype(float).to_numpy()
    ask = out["best_ask"].astype(float).to_numpy()
    horizon_ns = int(float(horizon_sec) * 1_000_000_000)
    latency_ns = int(float(latency_sec) * 1_000_000_000)

    entry_target = ts_ns + latency_ns
    exit_target = ts_ns + horizon_ns
    entry_idx = np.searchsorted(ts_ns, entry_target, side="left")
    exit_idx = np.searchsorted(ts_ns, exit_target, side="left")
    valid = (entry_idx < len(out)) & (exit_idx < len(out)) & (entry_target < exit_target)

    signal = np.zeros(len(out), dtype=int)
    entry_px = np.full(len(out), np.nan, dtype=float)
    exit_px = np.full(len(out), np.nan, dtype=float)
    gross = np.zeros(len(out), dtype=float)
    next_allowed = -np.inf

    raw = out["raw_signal"].to_numpy(dtype=int)
    for i, (sig, ts) in enumerate(zip(raw, ts_ns)):
        if sig == 0 or ts < next_allowed or not valid[i]:
            continue
        ei = int(entry_idx[i])
        xi = int(exit_idx[i])
        if sig > 0:
            ep = ask[ei]
            xp = bid[xi]
            pnl = (xp - ep) / ep * 10000.0
        else:
            ep = bid[ei]
            xp = ask[xi]
            pnl = (ep - xp) / ep * 10000.0
        if not (np.isfinite(ep) and np.isfinite(xp) and ep > 0 and xp > 0):
            continue
        signal[i] = int(sig)
        entry_px[i] = float(ep)
        exit_px[i] = float(xp)
        gross[i] = float(pnl)
        next_allowed = int(ts) + horizon_ns

    out["signal"] = signal
    out["traded"] = (out["signal"] != 0).astype(int)
    out["entry_px_taker"] = entry_px
    out["exit_px_taker"] = exit_px
    out["latency_sec"] = float(latency_sec)
    out["gross_pnl_bps"] = gross
    out["cost_bps"] = out["traded"] * float(cost_bps)
    out["net_pnl_bps"] = out["gross_pnl_bps"] - out["cost_bps"]
    out.loc[out["traded"] == 0, ["gross_pnl_bps", "cost_bps", "net_pnl_bps"]] = 0.0
    out["equity_bps"] = out["net_pnl_bps"].cumsum()
    metrics = summarize_trades(out)
    metrics.update(
        {
            "mode": "taker_bidask_non_overlap",
            "edge_threshold": float(edge_threshold),
            "cost_bps": float(cost_bps),
            "horizon_sec": float(horizon_sec),
            "latency_sec": float(latency_sec),
        }
    )
    return out, metrics


def sweep_taker_bidask(
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
                _, metrics = backtest_taker_bidask_non_overlapping(
                    predictions,
                    cost_bps=float(cost),
                    edge_threshold=float(edge),
                    horizon_sec=float(horizon_sec),
                    latency_sec=float(latency),
                )
                records.append(metrics)
    frame = pd.DataFrame(records)
    if frame.empty:
        return frame
    frame["rank_score"] = (
        frame["mean_net_pnl_bps"].astype(float).clip(-10, 10)
        + 0.002 * frame["total_net_pnl_bps"].astype(float).clip(-1000, 1000)
        + 0.05 * frame["hit_rate"].astype(float)
        - 0.01 * frame["max_drawdown_bps"].astype(float).abs().clip(0, 1000)
    )
    return frame.sort_values(["rank_score", "total_net_pnl_bps"], ascending=[False, False]).reset_index(drop=True)


def robust_profit_gate(
    sweep: pd.DataFrame,
    *,
    min_trades: int = 20,
    min_mean_net_bps: float = 0.0,
    min_total_net_bps: float = 0.0,
    group_col: str = "edge_threshold",
) -> dict[str, object]:
    if sweep.empty or group_col not in sweep.columns:
        return {"passed": False, "reason": "empty sweep"}
    candidates: list[dict[str, object]] = []
    for value, grp in sweep.groupby(group_col):
        viable = grp[grp["trades"].astype(float) >= float(min_trades)]
        if viable.empty:
            candidate = {
                group_col: float(value),
                "cells": int(len(grp)),
                "viable_cells": 0,
                "passed": False,
                "reason": "no cell has enough trades",
            }
        else:
            min_mean = float(viable["mean_net_pnl_bps"].min())
            min_total = float(viable["total_net_pnl_bps"].min())
            candidate = {
                group_col: float(value),
                "cells": int(len(grp)),
                "viable_cells": int(len(viable)),
                "min_trades": float(viable["trades"].min()),
                "min_mean_net_pnl_bps": min_mean,
                "median_mean_net_pnl_bps": float(viable["mean_net_pnl_bps"].median()),
                "min_total_net_pnl_bps": min_total,
                "positive_mean_cells": int((viable["mean_net_pnl_bps"].astype(float) > 0).sum()),
                "positive_total_cells": int((viable["total_net_pnl_bps"].astype(float) > 0).sum()),
                "passed": bool(min_mean > min_mean_net_bps and min_total > min_total_net_bps and len(viable) == len(grp)),
            }
        candidates.append(candidate)
    candidates = sorted(
        candidates,
        key=lambda r: (
            bool(r.get("passed", False)),
            float(r.get("min_mean_net_pnl_bps", -9999.0)),
            float(r.get("min_total_net_pnl_bps", -9999.0)),
        ),
        reverse=True,
    )
    best = candidates[0] if candidates else None
    return {"passed": bool(best and best.get("passed")), "best_candidate": best, "candidates": candidates}


def write_json(path: str | Path, payload: dict[str, object]) -> None:
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
