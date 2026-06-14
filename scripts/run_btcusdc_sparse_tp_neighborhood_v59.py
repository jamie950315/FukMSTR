from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_sparse_tp import (
    SparseTakeProfitPolicy,
    apply_take_profit_exit,
    build_sparse_abs_return_entries,
    summarize_sparse_tp_outcomes,
)


ROOT = Path(__file__).resolve().parents[1]
INPUT_BARS = ROOT / "runs" / "research_v48_btcusdc_full_1m_direct_ml_input" / "btcusdc_full_1m_bars.csv"
OUT_DIR = ROOT / "runs" / "research_v59_btcusdc_sparse_tp_neighborhood_audit"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V59_NEIGHBORHOOD_AUDIT_RESULTS.md"

FOLDS = (
    (1, "2024-01-05", "2025-04-04", "2025-04-04", "2025-06-03"),
    (2, "2024-03-05", "2025-06-03", "2025-06-03", "2025-08-02"),
    (3, "2024-05-04", "2025-08-02", "2025-08-02", "2025-10-01"),
    (4, "2024-07-03", "2025-10-01", "2025-10-01", "2025-11-30"),
    (5, "2024-09-01", "2025-11-30", "2025-11-30", "2026-01-29"),
    (6, "2024-10-31", "2026-01-29", "2026-01-29", "2026-03-30"),
    (7, "2024-12-30", "2026-03-30", "2026-03-30", "2026-05-29"),
)

LOOKBACKS = (720, 1080, 1440, 2160, 2880)
QUANTILES = (0.9900, 0.9925, 0.9950, 0.9975, 0.9990)
DIRECTIONS = ("reversal", "momentum")
SELECTED = {"lookback_minutes": 1440, "quantile": 0.995, "direction": "reversal"}


def _load_bars() -> pd.DataFrame:
    bars = pd.read_csv(INPUT_BARS, parse_dates=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    for col in ["open", "high", "low", "close", "volume"]:
        bars[col] = pd.to_numeric(bars[col], errors="coerce")
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars["replay_date"] = bars["timestamp"].dt.date.astype(str)
    return bars


def _basic_gate(summary: dict[str, object]) -> bool:
    return (
        int(summary["trades"]) >= 11
        and float(summary["win_rate"]) >= 0.90
        and float(summary["total_net_pnl_bps"]) >= 175.0
        and float(summary["mean_net_pnl_bps"]) >= 15.0
    )


def _write_report(payload: dict[str, object], top: pd.DataFrame, selected_row: dict[str, object]) -> None:
    lines = [
        "# Research V59 Neighborhood Audit Results",
        "",
        "## Purpose",
        "",
        "V59 checks whether the fixed V55/V57 sparse BTCUSDC rule is isolated within a nearby parameter family.",
        "",
        "This is an audit only. It does not promote or replace the V55/V57 fixed rule.",
        "",
        "## Fixed Components",
        "",
        "- Bars: Binance public 1m kline cache",
        "- Entry: next open",
        "- Exit: TP80, no stop loss",
        "- Horizon reserve: 1440 minutes",
        "- Feature: abs_return_bps",
        "",
        "## Grid",
        "",
        f"- Lookbacks: `{list(LOOKBACKS)}`",
        f"- Quantiles: `{list(QUANTILES)}`",
        f"- Directions: `{list(DIRECTIONS)}`",
        f"- Total candidates: `{payload['total_candidates']}`",
        "",
        "## Selected Rule Position",
        "",
        f"- Selected rule rank by total pnl: `{selected_row['rank_total_net_pnl']}`",
        f"- Selected trades: `{selected_row['trades']}`",
        f"- Selected wins: `{selected_row['wins']}`",
        f"- Selected win rate: `{float(selected_row['win_rate']):.6f}`",
        f"- Selected total net pnl: `{float(selected_row['total_net_pnl_bps']):.6f}` bps",
        f"- Selected basic gate screen: `{bool(selected_row['basic_gate_screen'])}`",
        "",
        "## Family Summary",
        "",
        f"- Basic gate screen pass count: `{payload['basic_gate_pass_count']}`",
        f"- Candidates with 11 wins: `{payload['eleven_win_count']}`",
        f"- Candidates matching selected total pnl or better: `{payload['total_ge_selected_count']}`",
        f"- Reversal basic gate pass count: `{payload['reversal_basic_gate_pass_count']}`",
        f"- Momentum basic gate pass count: `{payload['momentum_basic_gate_pass_count']}`",
        "",
        "## Top 10 By Total Pnl",
        "",
        top.to_markdown(index=False),
        "",
        "## Files",
        "",
        f"- Candidate evaluations: `{payload['candidate_evaluations_path']}`",
        f"- Summary JSON: `{payload['summary_path']}`",
        "",
        "## Caveat",
        "",
        "A neighborhood audit can show isolation or nearby support, but it still reuses the same historical sample and does not create more observed trades.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    bars = _load_bars()
    policy = SparseTakeProfitPolicy(take_profit_bps=80.0, horizon_minutes=1440)
    rows: list[dict[str, object]] = []

    for direction in DIRECTIONS:
        for lookback in LOOKBACKS:
            for quantile in QUANTILES:
                entries = build_sparse_abs_return_entries(
                    bars,
                    folds=FOLDS,
                    entry_delay_minutes=1,
                    lookback_minutes=int(lookback),
                    horizon_minutes=1440,
                    quantile=float(quantile),
                    direction=str(direction),
                )
                ledger = apply_take_profit_exit(entries, bars, policy)
                summary = summarize_sparse_tp_outcomes(ledger, quote_surcharge_bps=0.5)
                rows.append(
                    {
                        "direction": str(direction),
                        "lookback_minutes": int(lookback),
                        "quantile": float(quantile),
                        **summary,
                        "basic_gate_screen": bool(_basic_gate(summary)),
                    }
                )

    evaluations = pd.DataFrame(rows)
    evaluations = evaluations.sort_values(
        ["total_net_pnl_bps", "wins", "trades", "direction", "lookback_minutes", "quantile"],
        ascending=[False, False, False, True, True, True],
    ).reset_index(drop=True)
    evaluations["rank_total_net_pnl"] = range(1, len(evaluations) + 1)

    eval_path = OUT_DIR / "v59_neighborhood_candidate_evaluations.csv"
    evaluations.to_csv(eval_path, index=False)

    selected_mask = (
        (evaluations["direction"] == SELECTED["direction"])
        & (evaluations["lookback_minutes"].astype(int) == int(SELECTED["lookback_minutes"]))
        & (evaluations["quantile"].astype(float).round(4) == float(SELECTED["quantile"]))
    )
    if not selected_mask.any():
        raise SystemExit("selected V55/V57 rule missing from V59 evaluations")
    selected_row = evaluations.loc[selected_mask].iloc[0].to_dict()
    selected_total = float(selected_row["total_net_pnl_bps"])

    payload: dict[str, object] = {
        "input_bars": str(INPUT_BARS),
        "bar_rows": int(len(bars)),
        "candidate_evaluations_path": str(eval_path),
        "summary_path": str(OUT_DIR / "v59_summary.json"),
        "total_candidates": int(len(evaluations)),
        "selected_rule": selected_row,
        "basic_gate_pass_count": int(evaluations["basic_gate_screen"].astype(bool).sum()),
        "eleven_win_count": int((pd.to_numeric(evaluations["wins"], errors="coerce") >= 11).sum()),
        "total_ge_selected_count": int((pd.to_numeric(evaluations["total_net_pnl_bps"], errors="coerce") >= selected_total).sum()),
        "reversal_basic_gate_pass_count": int(evaluations.loc[evaluations["direction"] == "reversal", "basic_gate_screen"].astype(bool).sum()),
        "momentum_basic_gate_pass_count": int(evaluations.loc[evaluations["direction"] == "momentum", "basic_gate_screen"].astype(bool).sum()),
    }
    (OUT_DIR / "v59_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload, evaluations.head(10), selected_row)
    print(json.dumps(payload, indent=2))
