from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import summarize_trades
from .data_schema import timestamps_to_ns


@dataclass(frozen=True)
class ExitLockSpec:
    """Slot-preserving bracket exit policy for an already selected signal stream.

    The entry slot is still reserved until the original horizon even when a take-profit or stop-loss exits early.
    This prevents an early exit from creating extra overlapping opportunities during research audits.
    Use a non-finite or non-positive threshold to disable that side of the bracket.
    """

    take_profit_bps: float = 40.0
    stop_loss_bps: float = 0.0
    reserve_horizon: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @property
    def has_take_profit(self) -> bool:
        return np.isfinite(float(self.take_profit_bps)) and float(self.take_profit_bps) > 0.0

    @property
    def has_stop_loss(self) -> bool:
        return np.isfinite(float(self.stop_loss_bps)) and float(self.stop_loss_bps) > 0.0


def execution_path_arrays(frame: pd.DataFrame, *, horizon_sec: float, latency_sec: float):
    ts = timestamps_to_ns(frame["timestamp"])
    bid = frame["best_bid"].astype(float).to_numpy()
    ask = frame["best_ask"].astype(float).to_numpy()
    horizon_ns = int(float(horizon_sec) * 1_000_000_000)
    latency_ns = int(float(latency_sec) * 1_000_000_000)
    entry_target = ts + latency_ns
    exit_target = ts + horizon_ns
    entry_idx = np.searchsorted(ts, entry_target, side="left")
    exit_idx = np.searchsorted(ts, exit_target, side="left")
    valid = (entry_idx < len(ts)) & (exit_idx < len(ts)) & (entry_target < exit_target)
    return ts, bid, ask, entry_idx, exit_idx, valid, horizon_ns


def fast_exit_lock_metrics(
    raw: np.ndarray,
    arrays,
    *,
    cost_bps: float,
    spec: ExitLockSpec,
) -> tuple[dict[str, float], np.ndarray, list[str], np.ndarray]:
    ts, bid, ask, entry_idx, exit_idx, valid, horizon_ns = arrays
    pnls: list[float] = []
    reasons: list[str] = []
    holds: list[float] = []
    next_allowed = -10**30
    tp_on = spec.has_take_profit
    sl_on = spec.has_stop_loss
    tp_bps = float(spec.take_profit_bps)
    sl_bps = float(spec.stop_loss_bps)

    raw_arr = np.asarray(raw, dtype=int)
    for i in np.flatnonzero(raw_arr != 0):
        sig = int(np.clip(raw_arr[i], -1, 1))
        if int(ts[i]) < next_allowed or not bool(valid[i]):
            continue
        ei = int(entry_idx[i])
        xi = int(exit_idx[i])
        if xi <= ei:
            continue
        reason = "horizon"
        x = xi
        if sig > 0:
            ep = float(ask[ei])
            if not (np.isfinite(ep) and ep > 0):
                continue
            tp_px = ep * (1.0 + tp_bps / 10000.0) if tp_on else np.inf
            sl_px = ep * (1.0 - sl_bps / 10000.0) if sl_on else -np.inf
            for j in range(ei + 1, xi + 1):
                # Conservative same-tick ordering: adverse stop before favorable take-profit.
                if sl_on and float(bid[j]) <= sl_px:
                    x = j
                    reason = "stop_loss"
                    break
                if tp_on and float(bid[j]) >= tp_px:
                    x = j
                    reason = "take_profit"
                    break
            xp = float(bid[x])
            pnl = (xp - ep) / ep * 10000.0
        else:
            ep = float(bid[ei])
            if not (np.isfinite(ep) and ep > 0):
                continue
            tp_px = ep * (1.0 - tp_bps / 10000.0) if tp_on else -np.inf
            sl_px = ep * (1.0 + sl_bps / 10000.0) if sl_on else np.inf
            for j in range(ei + 1, xi + 1):
                if sl_on and float(ask[j]) >= sl_px:
                    x = j
                    reason = "stop_loss"
                    break
                if tp_on and float(ask[j]) <= tp_px:
                    x = j
                    reason = "take_profit"
                    break
            xp = float(ask[x])
            pnl = (ep - xp) / ep * 10000.0
        if np.isfinite(xp) and xp > 0:
            pnls.append(float(pnl) - float(cost_bps))
            reasons.append(reason)
            holds.append(float((int(ts[x]) - int(ts[ei])) / 1_000_000_000.0))
            next_allowed = int(ts[i]) + int(horizon_ns) if spec.reserve_horizon else int(ts[x])
    arr = np.asarray(pnls, dtype=float)
    if len(arr) == 0:
        return {
            "events": float(len(raw)),
            "trades": 0.0,
            "hit_rate": 0.0,
            "mean_net_pnl_bps": 0.0,
            "median_net_pnl_bps": 0.0,
            "total_net_pnl_bps": 0.0,
            "max_drawdown_bps": 0.0,
            "profit_factor": 0.0,
            "take_profit_exits": 0.0,
            "stop_loss_exits": 0.0,
            "horizon_exits": 0.0,
            "mean_hold_sec": 0.0,
        }, arr, reasons, np.asarray(holds, dtype=float)
    equity = np.cumsum(arr)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    gross_profit = float(arr[arr > 0].sum())
    gross_loss = float(-arr[arr < 0].sum())
    metrics = {
        "events": float(len(raw)),
        "trades": float(len(arr)),
        "hit_rate": float((arr > 0).mean()),
        "mean_net_pnl_bps": float(arr.mean()),
        "median_net_pnl_bps": float(np.median(arr)),
        "total_net_pnl_bps": float(arr.sum()),
        "max_drawdown_bps": float(dd.min()) if len(dd) else 0.0,
        "profit_factor": float(gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0),
        "take_profit_exits": float(sum(1 for r in reasons if r == "take_profit")),
        "stop_loss_exits": float(sum(1 for r in reasons if r == "stop_loss")),
        "horizon_exits": float(sum(1 for r in reasons if r == "horizon")),
        "mean_hold_sec": float(np.mean(holds)) if holds else 0.0,
    }
    return metrics, arr, reasons, np.asarray(holds, dtype=float)


def backtest_fixed_signals_taker_bidask_exit_lock(
    predictions: pd.DataFrame,
    *,
    cost_bps: float,
    horizon_sec: float,
    latency_sec: float,
    spec: ExitLockSpec,
    timestamp_col: str = "timestamp",
) -> tuple[pd.DataFrame, dict[str, float]]:
    required = {timestamp_col, "best_bid", "best_ask", "signal"}
    missing = required.difference(predictions.columns)
    if missing:
        raise ValueError(f"prediction frame missing columns for exit-lock execution: {sorted(missing)}")
    frame = predictions.copy().sort_values(timestamp_col).reset_index(drop=True)
    if timestamp_col != "timestamp":
        frame = frame.rename(columns={timestamp_col: "timestamp"})
    raw = frame["signal"].fillna(0).astype(int).clip(-1, 1).to_numpy()
    arrays = execution_path_arrays(frame, horizon_sec=horizon_sec, latency_sec=latency_sec)
    ts, bid, ask, entry_idx, exit_idx, valid, horizon_ns = arrays

    kept = np.zeros(len(frame), dtype=int)
    entry_px = np.full(len(frame), np.nan, dtype=float)
    exit_px = np.full(len(frame), np.nan, dtype=float)
    gross = np.zeros(len(frame), dtype=float)
    hold_sec = np.zeros(len(frame), dtype=float)
    exit_reason = ["" for _ in range(len(frame))]
    next_allowed = -10**30
    tp_on = spec.has_take_profit
    sl_on = spec.has_stop_loss
    tp_bps = float(spec.take_profit_bps)
    sl_bps = float(spec.stop_loss_bps)

    for i, sig in enumerate(raw):
        sig = int(np.clip(sig, -1, 1))
        if sig == 0 or int(ts[i]) < next_allowed or not bool(valid[i]):
            continue
        ei = int(entry_idx[i])
        xi = int(exit_idx[i])
        if xi <= ei:
            continue
        reason = "horizon"
        x = xi
        if sig > 0:
            ep = float(ask[ei])
            if not (np.isfinite(ep) and ep > 0):
                continue
            tp_px = ep * (1.0 + tp_bps / 10000.0) if tp_on else np.inf
            sl_px = ep * (1.0 - sl_bps / 10000.0) if sl_on else -np.inf
            for j in range(ei + 1, xi + 1):
                if sl_on and float(bid[j]) <= sl_px:
                    x = j; reason = "stop_loss"; break
                if tp_on and float(bid[j]) >= tp_px:
                    x = j; reason = "take_profit"; break
            xp = float(bid[x])
            pnl = (xp - ep) / ep * 10000.0
        else:
            ep = float(bid[ei])
            if not (np.isfinite(ep) and ep > 0):
                continue
            tp_px = ep * (1.0 - tp_bps / 10000.0) if tp_on else -np.inf
            sl_px = ep * (1.0 + sl_bps / 10000.0) if sl_on else np.inf
            for j in range(ei + 1, xi + 1):
                if sl_on and float(ask[j]) >= sl_px:
                    x = j; reason = "stop_loss"; break
                if tp_on and float(ask[j]) <= tp_px:
                    x = j; reason = "take_profit"; break
            xp = float(ask[x])
            pnl = (ep - xp) / ep * 10000.0
        if not (np.isfinite(xp) and xp > 0):
            continue
        kept[i] = sig
        entry_px[i] = ep
        exit_px[i] = xp
        gross[i] = float(pnl)
        exit_reason[i] = reason
        hold_sec[i] = float((int(ts[x]) - int(ts[ei])) / 1_000_000_000.0)
        next_allowed = int(ts[i]) + int(horizon_ns) if spec.reserve_horizon else int(ts[x])

    frame["raw_selective_signal"] = raw
    frame["signal"] = kept
    frame["traded"] = (kept != 0).astype(int)
    frame["entry_px_taker"] = entry_px
    frame["exit_px_taker"] = exit_px
    frame["gross_pnl_bps"] = gross
    frame["cost_bps"] = frame["traded"] * float(cost_bps)
    frame["net_pnl_bps"] = frame["gross_pnl_bps"] - frame["cost_bps"]
    frame.loc[frame["traded"] == 0, ["gross_pnl_bps", "cost_bps", "net_pnl_bps"]] = 0.0
    frame["equity_bps"] = frame["net_pnl_bps"].cumsum()
    frame["exit_reason"] = exit_reason
    frame["hold_sec"] = hold_sec
    frame["take_profit_bps"] = float(spec.take_profit_bps)
    frame["stop_loss_bps"] = float(spec.stop_loss_bps)
    frame["reserve_horizon"] = bool(spec.reserve_horizon)
    metrics = summarize_trades(frame)
    metrics.update(
        {
            "mode": "exit_lock_taker_bidask_non_overlap",
            "cost_bps": float(cost_bps),
            "horizon_sec": float(horizon_sec),
            "latency_sec": float(latency_sec),
            "take_profit_bps": float(spec.take_profit_bps),
            "stop_loss_bps": float(spec.stop_loss_bps),
            "reserve_horizon": bool(spec.reserve_horizon),
            "take_profit_exits": float((frame.loc[frame["traded"] == 1, "exit_reason"] == "take_profit").sum()),
            "stop_loss_exits": float((frame.loc[frame["traded"] == 1, "exit_reason"] == "stop_loss").sum()),
            "horizon_exits": float((frame.loc[frame["traded"] == 1, "exit_reason"] == "horizon").sum()),
            "mean_hold_sec": float(frame.loc[frame["traded"] == 1, "hold_sec"].mean()) if int(frame["traded"].sum()) else 0.0,
        }
    )
    return frame, metrics
