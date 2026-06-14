from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from .data_schema import timestamps_to_ns


def audit_trade_backtest(
    *,
    backtest_csv: str | Path,
    out_dir: str | Path,
    horizon_sec: float | None = None,
    latency_sec: float | None = None,
    clean: bool = False,
) -> dict[str, object]:
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(backtest_csv)
    if "traded" not in frame.columns or "net_pnl_bps" not in frame.columns:
        raise ValueError("backtest CSV must contain traded and net_pnl_bps columns")
    enriched = enrich_trade_paths(frame, horizon_sec=horizon_sec, latency_sec=latency_sec)
    trades = enriched.loc[enriched["traded"].astype(int) == 1].copy()
    summary = summarize_trade_ledger(trades)
    side_fold = side_fold_summary(trades)
    trades.to_csv(out / "trade_ledger_enriched.csv", index=False)
    side_fold.to_csv(out / "side_fold_summary.csv", index=False)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_trade_audit_report(out / "REPORT.md", summary, trades, side_fold)
    return {"out_dir": str(out), "summary": summary}


def enrich_trade_paths(frame: pd.DataFrame, *, horizon_sec: float | None = None, latency_sec: float | None = None) -> pd.DataFrame:
    """Add MFE/MAE-style path diagnostics for traded rows using bid/ask marks.

    This function uses only the already packaged backtest frame.  It does not change PnL; it
    describes what happened inside each holding window after the signal fired.
    """
    out = frame.copy().sort_values("timestamp").reset_index(drop=True)
    for col in ["path_mfe_gross_bps", "path_mae_gross_bps", "path_end_gross_bps"]:
        out[col] = np.nan
    out["adverse_before_favorable"] = pd.Series([pd.NA] * len(out), dtype="boolean")
    required = {"timestamp", "best_bid", "best_ask", "signal", "entry_px_taker"}
    if required.difference(out.columns):
        return out
    ts_ns = timestamps_to_ns(out["timestamp"])
    bid = pd.to_numeric(out["best_bid"], errors="coerce").to_numpy(dtype=float)
    ask = pd.to_numeric(out["best_ask"], errors="coerce").to_numpy(dtype=float)
    signals = pd.to_numeric(out["signal"], errors="coerce").fillna(0).astype(int).to_numpy()
    entry_px = pd.to_numeric(out["entry_px_taker"], errors="coerce").to_numpy(dtype=float)
    if horizon_sec is None:
        if "horizon_sec" in out.columns and pd.to_numeric(out["horizon_sec"], errors="coerce").notna().any():
            horizon_sec = float(pd.to_numeric(out["horizon_sec"], errors="coerce").dropna().iloc[0])
        else:
            return out
    if latency_sec is None:
        if "latency_sec" in out.columns and pd.to_numeric(out["latency_sec"], errors="coerce").notna().any():
            latency_sec = float(pd.to_numeric(out["latency_sec"], errors="coerce").dropna().iloc[0])
        else:
            latency_sec = 0.0
    horizon_ns = int(float(horizon_sec) * 1_000_000_000)
    latency_ns = int(float(latency_sec) * 1_000_000_000)
    traded_idx = np.flatnonzero(pd.to_numeric(out.get("traded", 0), errors="coerce").fillna(0).astype(int).to_numpy() == 1)
    for i in traded_idx:
        sig = int(signals[i])
        ep = float(entry_px[i])
        if sig == 0 or not np.isfinite(ep) or ep <= 0:
            continue
        start_idx = int(np.searchsorted(ts_ns, ts_ns[i] + latency_ns, side="left"))
        end_idx = int(np.searchsorted(ts_ns, ts_ns[i] + horizon_ns, side="left"))
        if start_idx >= len(out) or end_idx >= len(out) or end_idx < start_idx:
            continue
        if sig > 0:
            path = (bid[start_idx : end_idx + 1] - ep) / ep * 10000.0
        else:
            path = (ep - ask[start_idx : end_idx + 1]) / ep * 10000.0
        path = path[np.isfinite(path)]
        if len(path) == 0:
            continue
        out.at[i, "path_mfe_gross_bps"] = float(np.max(path))
        out.at[i, "path_mae_gross_bps"] = float(np.min(path))
        out.at[i, "path_end_gross_bps"] = float(path[-1])
        max_pos = int(np.argmax(path))
        min_pos = int(np.argmin(path))
        out.at[i, "adverse_before_favorable"] = bool(min_pos < max_pos)
    return out


def summarize_trade_ledger(trades: pd.DataFrame) -> dict[str, object]:
    summary: dict[str, object] = {}
    if trades.empty:
        return {"trades": 0}
    pnl = pd.to_numeric(trades["net_pnl_bps"], errors="coerce").fillna(0.0)
    summary["trades"] = int(len(trades))
    summary["total_net_pnl_bps"] = float(pnl.sum())
    summary["mean_net_pnl_bps"] = float(pnl.mean())
    summary["median_net_pnl_bps"] = float(pnl.median())
    summary["hit_rate"] = float((pnl > 0).mean())
    summary["std_net_pnl_bps"] = float(pnl.std(ddof=0)) if len(pnl) else 0.0
    summary["profit_factor"] = _profit_factor(pnl)
    summary["max_drawdown_bps"] = _max_drawdown(pnl)
    summary["long_trades"] = int((trades["signal"].astype(int) > 0).sum()) if "signal" in trades.columns else 0
    summary["short_trades"] = int((trades["signal"].astype(int) < 0).sum()) if "signal" in trades.columns else 0
    summary["long_total_net_pnl_bps"] = float(pnl[trades["signal"].astype(int) > 0].sum()) if "signal" in trades.columns else 0.0
    summary["short_total_net_pnl_bps"] = float(pnl[trades["signal"].astype(int) < 0].sum()) if "signal" in trades.columns else 0.0
    summary["best_trade_bps"] = float(pnl.max())
    summary["worst_trade_bps"] = float(pnl.min())
    summary["p05_trade_bps"] = float(pnl.quantile(0.05))
    summary["p95_trade_bps"] = float(pnl.quantile(0.95))
    gains = pnl[pnl > 0].sort_values(ascending=False)
    if len(gains):
        summary["top1_gain_share"] = float(gains.iloc[0] / gains.sum()) if gains.sum() > 0 else 0.0
        summary["top3_gain_share"] = float(gains.head(3).sum() / gains.sum()) if gains.sum() > 0 else 0.0
    losses = -pnl[pnl < 0].sort_values()
    if len(losses):
        summary["top1_loss_share"] = float(losses.iloc[0] / losses.sum()) if losses.sum() > 0 else 0.0
        summary["top3_loss_share"] = float(losses.head(3).sum() / losses.sum()) if losses.sum() > 0 else 0.0
    summary["max_win_streak"] = int(_max_streak(pnl > 0))
    summary["max_loss_streak"] = int(_max_streak(pnl <= 0))
    if "fold" in trades.columns:
        fold_totals = trades.assign(_pnl=pnl).groupby("fold")["_pnl"].sum()
        summary["fold_count"] = int(fold_totals.size)
        summary["fold_total_min_bps"] = float(fold_totals.min())
        summary["fold_total_max_bps"] = float(fold_totals.max())
    for col in ["path_mfe_gross_bps", "path_mae_gross_bps", "path_end_gross_bps"]:
        if col in trades.columns:
            values = pd.to_numeric(trades[col], errors="coerce").dropna()
            if len(values):
                summary[f"{col}_mean"] = float(values.mean())
                summary[f"{col}_median"] = float(values.median())
                summary[f"{col}_min"] = float(values.min())
                summary[f"{col}_max"] = float(values.max())
    if "adverse_before_favorable" in trades.columns:
        values = trades["adverse_before_favorable"].dropna()
        if len(values):
            summary["adverse_before_favorable_rate"] = float(values.astype(bool).mean())
    return summary


def side_fold_summary(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    frame = trades.copy()
    frame["side"] = np.where(frame["signal"].astype(int) > 0, "long", np.where(frame["signal"].astype(int) < 0, "short", "flat"))
    keys = ["side"]
    if "fold" in frame.columns:
        keys = ["fold", "side"]
    grouped = frame.groupby(keys, dropna=False)["net_pnl_bps"].agg(["count", "mean", "median", "sum", "min", "max"]).reset_index()
    grouped = grouped.rename(columns={"count": "trades", "sum": "total_net_pnl_bps", "mean": "mean_net_pnl_bps", "median": "median_net_pnl_bps", "min": "worst_trade_bps", "max": "best_trade_bps"})
    return grouped


def write_trade_audit_report(path: str | Path, summary: dict[str, object], trades: pd.DataFrame, side_fold: pd.DataFrame) -> None:
    lines = ["# Trade Audit Report", "", "## Summary", "", "```json", json.dumps(summary, indent=2), "```", ""]
    lines.extend(["## Side/fold breakdown", ""])
    lines.append(side_fold.to_markdown(index=False) if not side_fold.empty else "No side/fold rows.")
    lines.extend(["", "## Worst trades", ""])
    if not trades.empty:
        cols = [c for c in ["fold", "timestamp", "signal", "net_pnl_bps", "gross_pnl_bps", "path_mfe_gross_bps", "path_mae_gross_bps"] if c in trades.columns]
        lines.append(trades.sort_values("net_pnl_bps")[cols].head(10).to_markdown(index=False))
        lines.extend(["", "## Best trades", ""])
        lines.append(trades.sort_values("net_pnl_bps", ascending=False)[cols].head(10).to_markdown(index=False))
    else:
        lines.append("No trades.")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def _profit_factor(pnl: pd.Series) -> float:
    gains = float(pnl[pnl > 0].sum())
    losses = float(-pnl[pnl < 0].sum())
    if losses <= 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def _max_drawdown(pnl: pd.Series) -> float:
    if len(pnl) == 0:
        return 0.0
    equity = pnl.cumsum().to_numpy(dtype=float)
    peak = np.maximum.accumulate(equity)
    return float((equity - peak).min())


def _max_streak(mask: pd.Series | np.ndarray) -> int:
    arr = np.asarray(mask, dtype=bool)
    best = current = 0
    for value in arr:
        if value:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return int(best)
