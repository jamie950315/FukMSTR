from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import (
    BTCUSDCCandidate,
    build_delayed_candidate_trade_ledger,
    candidate_grid_from_calibration,
    summarize_fixed_policy_stability,
)


ROOT = Path(__file__).resolve().parents[1]
INPUT_BARS = ROOT / "runs" / "research_v50_btcusdc_full_aggtrade_flow_input" / "btcusdc_full_aggtrade_1m_flow_bars.csv"
OUT_DIR = ROOT / "runs" / "research_v68_btcusdc_fixed_flow_stability"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V68_FIXED_FLOW_STABILITY_RESULTS.md"

LOOKBACK_MINUTES = 1440
HORIZON_MINUTES = 720
DIRECTION = "flow_momentum"
FILTER_FEATURE = "range_bps"
QUANTILE = 0.9
FEE_BPS = 8.5
LEVERAGE = 8.0
FOLD_COUNT = 7
ENTRY_DELAYS = (0, 1, 2, 5, 10)
EXTRA_COST_BPS = (0.0, 4.0, 8.0, 16.0)


def _load_bars(path: Path) -> pd.DataFrame:
    bars = pd.read_csv(path)
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    if "replay_date" not in bars.columns:
        bars["replay_date"] = bars["timestamp"].dt.date.astype(str)
    return bars.sort_values("timestamp").reset_index(drop=True)


def _fixed_candidate(bars: pd.DataFrame) -> BTCUSDCCandidate:
    candidates = candidate_grid_from_calibration(
        bars,
        lookbacks=[LOOKBACK_MINUTES],
        horizons=[HORIZON_MINUTES],
        directions=[DIRECTION],
        filter_features=[FILTER_FEATURE],
        quantiles=[QUANTILE],
        fee_bps=FEE_BPS,
    )
    if len(candidates) != 1:
        raise ValueError(f"expected one fixed candidate, got {len(candidates)}")
    return candidates[0]


def _assign_date_folds(trades: pd.DataFrame, *, fold_count: int) -> pd.DataFrame:
    if trades.empty:
        out = trades.copy()
        out["fold"] = pd.Series(dtype=int)
        return out
    out = trades.copy()
    dates = np.array(sorted(out["replay_date"].astype(str).unique()))
    splits = [chunk for chunk in np.array_split(dates, int(fold_count)) if len(chunk)]
    date_to_fold: dict[str, int] = {}
    for fold, chunk in enumerate(splits, start=1):
        for day in chunk:
            date_to_fold[str(day)] = int(fold)
    out["fold"] = out["replay_date"].astype(str).map(date_to_fold).astype(int)
    return out


def _fold_summary(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=["fold", "start", "end", "trades", "total_net_pnl_bps", "account_return_pct", "win_rate"])
    rows: list[dict[str, object]] = []
    for fold, group in trades.groupby("fold", sort=True):
        pnl = pd.to_numeric(group["net_pnl_bps"], errors="coerce").fillna(0.0)
        rows.append(
            {
                "fold": int(fold),
                "start": str(group["timestamp"].min()),
                "end": str(group["timestamp"].max()),
                "trades": int(len(group)),
                "total_net_pnl_bps": float(pnl.sum()),
                "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                "account_return_pct": float(pnl.sum()) * LEVERAGE / 100.0,
                "win_rate": float((pnl > 0).mean()) if len(pnl) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _delay_summary(bars: pd.DataFrame, candidate: BTCUSDCCandidate) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    ledgers: list[pd.DataFrame] = []
    for delay in ENTRY_DELAYS:
        trades = build_delayed_candidate_trade_ledger(bars, candidate, entry_delay_minutes=int(delay))
        trades["entry_delay_minutes"] = int(delay)
        ledgers.append(trades)
        pnl = pd.to_numeric(trades.get("net_pnl_bps", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
        rows.append(
            {
                "entry_delay_minutes": int(delay),
                "trades": int(len(pnl)),
                "total_net_pnl_bps": float(pnl.sum()),
                "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                "account_return_pct": float(pnl.sum()) * LEVERAGE / 100.0,
                "win_rate": float((pnl > 0).mean()) if len(pnl) else 0.0,
            }
        )
    return pd.DataFrame(rows), pd.concat(ledgers, ignore_index=True) if ledgers else pd.DataFrame()


def _extra_cost_summary(base_trades: pd.DataFrame) -> pd.DataFrame:
    base = pd.to_numeric(base_trades.get("net_pnl_bps", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    rows = []
    for extra in EXTRA_COST_BPS:
        pnl = base - float(extra)
        rows.append(
            {
                "extra_cost_bps": float(extra),
                "trades": int(len(pnl)),
                "total_net_pnl_bps": float(pnl.sum()),
                "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                "account_return_pct": float(pnl.sum()) * LEVERAGE / 100.0,
                "win_rate": float((pnl > 0).mean()) if len(pnl) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _write_report(payload: dict[str, object], fold_summary: pd.DataFrame, delay_summary: pd.DataFrame, extra_cost_summary: pd.DataFrame) -> None:
    decision = payload["decision"]
    aggregate = payload["aggregate"]
    candidate = payload["candidate"]
    lines = [
        "# Research V68 Fixed Flow Stability Results",
        "",
        "## Decision",
        "",
        f"- Passed: `{decision['passed']}`",
        f"- Failed checks: `{';'.join(decision['failed_checks'])}`",
        "",
        "## Candidate",
        "",
        f"- Rule: `{candidate['lookback_minutes']}|{candidate['horizon_minutes']}|{candidate['direction']}|{candidate['filter_feature']}|q{candidate['quantile']}`",
        f"- Threshold: `{float(candidate['threshold']):.12f}`",
        f"- Fee: `{candidate['fee_bps']}` bps",
        "",
        "## Aggregate",
        "",
        f"- Trades: `{aggregate['trade_count']}`",
        f"- Total net pnl: `{float(aggregate['total_net_pnl_bps']):.6f}` bps",
        f"- Account return: `{float(aggregate['account_return_pct']):.6f}%`",
        f"- Mean net pnl: `{float(aggregate['mean_net_pnl_bps']):.6f}` bps",
        f"- Win rate: `{float(aggregate['win_rate']):.6f}`",
        f"- Active folds: `{decision['active_folds']}`",
        f"- Positive fold rate: `{float(decision['positive_fold_rate']):.6f}`",
        f"- Worst fold: `{float(decision['worst_fold_net_pnl_bps']):.6f}` bps",
        f"- Worst delay: `{float(decision['worst_delay_total_net_pnl_bps']):.6f}` bps",
        "",
        "## Fold Summary",
        "",
        fold_summary.to_csv(index=False).strip(),
        "",
        "## Delay Summary",
        "",
        delay_summary.to_csv(index=False).strip(),
        "",
        "## Extra Cost Summary",
        "",
        extra_cost_summary.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V68 is a fixed-policy audit on true BTCUSDC public aggTrade flow bars. It avoids validation-oracle candidate selection. A pass is a research candidate, not a live-profit guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    bars = _load_bars(INPUT_BARS)
    candidate = _fixed_candidate(bars)
    base_trades = build_delayed_candidate_trade_ledger(bars, candidate, entry_delay_minutes=0)
    base_trades = _assign_date_folds(base_trades, fold_count=FOLD_COUNT)
    folds = _fold_summary(base_trades)
    delays, delay_ledgers = _delay_summary(bars, candidate)
    extra = _extra_cost_summary(base_trades)
    decision = summarize_fixed_policy_stability(
        base_trades,
        fold_col="fold",
        delay_summary=delays,
        extra_cost_summary=extra,
    )
    pnl = pd.to_numeric(base_trades.get("net_pnl_bps", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    aggregate = {
        "trade_count": int(len(pnl)),
        "total_net_pnl_bps": float(pnl.sum()),
        "account_return_pct": float(pnl.sum()) * LEVERAGE / 100.0,
        "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
        "win_rate": float((pnl > 0).mean()) if len(pnl) else 0.0,
        "input_rows": int(len(bars)),
        "input_start": str(bars["timestamp"].min()),
        "input_end": str(bars["timestamp"].max()),
    }
    payload: dict[str, object] = {
        "version": "v68_btcusdc_fixed_flow_stability",
        "input_bars": str(INPUT_BARS),
        "candidate": candidate.to_dict(),
        "aggregate": aggregate,
        "decision": decision,
        "outputs": {
            "base_trade_ledger": str(OUT_DIR / "v68_base_trade_ledger.csv"),
            "fold_summary": str(OUT_DIR / "v68_fold_summary.csv"),
            "delay_summary": str(OUT_DIR / "v68_delay_summary.csv"),
            "delay_ledgers": str(OUT_DIR / "v68_delay_trade_ledgers.csv"),
            "extra_cost_summary": str(OUT_DIR / "v68_extra_cost_summary.csv"),
            "summary_json": str(OUT_DIR / "v68_summary.json"),
            "report": str(REPORT_PATH),
        },
    }
    base_trades.to_csv(OUT_DIR / "v68_base_trade_ledger.csv", index=False)
    folds.to_csv(OUT_DIR / "v68_fold_summary.csv", index=False)
    delays.to_csv(OUT_DIR / "v68_delay_summary.csv", index=False)
    delay_ledgers.to_csv(OUT_DIR / "v68_delay_trade_ledgers.csv", index=False)
    extra.to_csv(OUT_DIR / "v68_extra_cost_summary.csv", index=False)
    (OUT_DIR / "v68_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, folds, delays, extra)
    print(json.dumps(payload, indent=2, default=str))
