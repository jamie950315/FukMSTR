from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from .data_schema import timestamps_to_ns
from .trade_audit import side_fold_summary, summarize_trade_ledger, write_trade_audit_report


def combine_fixed_backtest_ledgers(
    *,
    backtest_paths: list[str | Path],
    horizon_secs: list[float],
    out_dir: str | Path,
    strategy_names: list[str] | None = None,
    clean: bool = False,
) -> dict[str, object]:
    """Combine already-repriced fixed-template ledgers with portfolio-level non-overlap.

    Each input ledger must contain rows from a taker/selective fixed-template backtest.  The
    combination uses existing trade PnL, then enforces one open position at a time across all
    strategies using each strategy's holding horizon.  Input order is the priority order when
    two signals occur at the same timestamp.
    """
    if len(backtest_paths) != len(horizon_secs):
        raise ValueError("backtest_paths and horizon_secs must have the same length")
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    strategy_names = strategy_names or [Path(p).parent.name for p in backtest_paths]
    if len(strategy_names) != len(backtest_paths):
        raise ValueError("strategy_names and backtest_paths must have the same length")

    proposals: list[pd.DataFrame] = []
    for priority, (path, horizon_sec, name) in enumerate(zip(backtest_paths, horizon_secs, strategy_names)):
        frame = pd.read_csv(path)
        if "traded" not in frame.columns or "timestamp" not in frame.columns:
            raise ValueError(f"ledger {path} missing traded/timestamp columns")
        trades = frame.loc[pd.to_numeric(frame["traded"], errors="coerce").fillna(0).astype(int) == 1].copy()
        if trades.empty:
            continue
        trades["strategy"] = str(name)
        trades["priority"] = int(priority)
        trades["horizon_sec"] = float(horizon_sec)
        trades["timestamp_ns"] = timestamps_to_ns(trades["timestamp"])
        proposals.append(trades)
    if proposals:
        all_props = pd.concat(proposals, ignore_index=True)
        all_props = all_props.sort_values(["timestamp_ns", "priority"]).reset_index(drop=True)
    else:
        all_props = pd.DataFrame()
    all_props.to_csv(out / "trade_proposals.csv", index=False)

    selected_rows: list[pd.Series] = []
    next_allowed_ns = -np.inf
    for _, row in all_props.iterrows():
        ts = int(row["timestamp_ns"])
        if ts < next_allowed_ns:
            continue
        selected_rows.append(row)
        next_allowed_ns = ts + int(float(row["horizon_sec"]) * 1_000_000_000)
    selected = pd.DataFrame(selected_rows).reset_index(drop=True) if selected_rows else pd.DataFrame()
    if not selected.empty:
        selected["portfolio_traded"] = 1
        selected["portfolio_equity_bps"] = pd.to_numeric(selected["net_pnl_bps"], errors="coerce").fillna(0.0).cumsum()
    selected.to_csv(out / "portfolio_trade_ledger.csv", index=False)
    summary = summarize_trade_ledger(selected) if not selected.empty else {"trades": 0}
    if not all_props.empty:
        summary["proposed_trades"] = int(len(all_props))
        summary["proposal_acceptance_rate"] = float(len(selected) / len(all_props)) if len(all_props) else 0.0
    by_strategy = _strategy_summary(selected)
    by_strategy.to_csv(out / "strategy_summary.csv", index=False)
    side_fold = side_fold_summary(selected) if not selected.empty else pd.DataFrame()
    side_fold.to_csv(out / "side_fold_summary.csv", index=False)
    result = {
        "out_dir": str(out),
        "inputs": [{"path": str(p), "horizon_sec": float(h), "strategy": str(n)} for p, h, n in zip(backtest_paths, horizon_secs, strategy_names)],
        "summary": summary,
    }
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_portfolio_report(out / "REPORT.md", result, selected, by_strategy, side_fold)
    return result


def _strategy_summary(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty or "strategy" not in trades.columns:
        return pd.DataFrame()
    grouped = trades.groupby("strategy")["net_pnl_bps"].agg(["count", "mean", "median", "sum", "min", "max"]).reset_index()
    grouped = grouped.rename(columns={"count": "trades", "mean": "mean_net_pnl_bps", "median": "median_net_pnl_bps", "sum": "total_net_pnl_bps", "min": "worst_trade_bps", "max": "best_trade_bps"})
    return grouped.sort_values("total_net_pnl_bps", ascending=False).reset_index(drop=True)


def write_portfolio_report(path: str | Path, result: dict[str, object], trades: pd.DataFrame, by_strategy: pd.DataFrame, side_fold: pd.DataFrame) -> None:
    lines = ["# Fixed-template Portfolio Ledger Audit", "", "This diagnostic combines already-priced fixed-template trades and enforces one open position at a time across strategies.", "", "## Summary", "", "```json", json.dumps(result.get("summary", {}), indent=2), "```", "", "## Strategy breakdown", ""]
    lines.append(by_strategy.to_markdown(index=False) if not by_strategy.empty else "No strategy rows.")
    lines.extend(["", "## Side/fold breakdown", ""])
    lines.append(side_fold.to_markdown(index=False) if not side_fold.empty else "No side/fold rows.")
    if not trades.empty:
        cols = [c for c in ["strategy", "fold", "timestamp", "signal", "horizon_sec", "net_pnl_bps", "portfolio_equity_bps"] if c in trades.columns]
        lines.extend(["", "## Selected trades", "", trades[cols].to_markdown(index=False)])
    Path(path).write_text("\n".join(lines), encoding="utf-8")
