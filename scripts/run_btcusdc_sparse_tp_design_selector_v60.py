from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_sparse_tp import (
    SparseTakeProfitPolicy,
    apply_take_profit_exit,
    build_sparse_abs_return_entries,
    summarize_sparse_tp_by_fold_sets,
    summarize_sparse_tp_outcomes,
)


ROOT = Path(__file__).resolve().parents[1]
INPUT_BARS = ROOT / "runs" / "research_v48_btcusdc_full_1m_direct_ml_input" / "btcusdc_full_1m_bars.csv"
OUT_DIR = ROOT / "runs" / "research_v60_btcusdc_sparse_tp_design_selector_audit"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V60_DESIGN_SELECTOR_AUDIT_RESULTS.md"

FOLDS = (
    (1, "2024-01-05", "2025-04-04", "2025-04-04", "2025-06-03"),
    (2, "2024-03-05", "2025-06-03", "2025-06-03", "2025-08-02"),
    (3, "2024-05-04", "2025-08-02", "2025-08-02", "2025-10-01"),
    (4, "2024-07-03", "2025-10-01", "2025-10-01", "2025-11-30"),
    (5, "2024-09-01", "2025-11-30", "2025-11-30", "2026-01-29"),
    (6, "2024-10-31", "2026-01-29", "2026-01-29", "2026-03-30"),
    (7, "2024-12-30", "2026-03-30", "2026-03-30", "2026-05-29"),
)

DESIGN_FOLDS = {1, 2, 3, 4}
HOLDOUT_FOLDS = {5, 6, 7}
LOOKBACKS = (720, 1080, 1440, 2160, 2880)
QUANTILES = (0.9900, 0.9925, 0.9950, 0.9975, 0.9990)
DIRECTIONS = ("reversal", "momentum")
FIXED_V55 = {"lookback_minutes": 1440, "quantile": 0.995, "direction": "reversal"}


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


def _prefixed_basic_gate(row: pd.Series, prefix: str) -> bool:
    return (
        int(row[f"{prefix}_trades"]) >= 1
        and float(row[f"{prefix}_win_rate"]) >= 0.90
        and float(row[f"{prefix}_total_net_pnl_bps"]) > 0.0
        and float(row[f"{prefix}_mean_net_pnl_bps"]) > 0.0
    )


def _write_report(payload: dict[str, object], design_top: pd.DataFrame) -> None:
    selected = payload["design_selected_rule"]
    fixed = payload["fixed_v55_rule"]
    lines = [
        "# Research V60 Design Selector Audit Results",
        "",
        "## Purpose",
        "",
        "V60 ranks the V59 parameter neighborhood using design folds only, then reports the selected candidate on holdout folds.",
        "",
        "This is an audit only. It does not promote or replace the V55/V57 fixed rule.",
        "",
        "## Split",
        "",
        f"- Design folds: `{sorted(DESIGN_FOLDS)}`",
        f"- Holdout folds: `{sorted(HOLDOUT_FOLDS)}`",
        f"- Total candidates: `{payload['total_candidates']}`",
        "",
        "## Design-Selected Candidate",
        "",
        f"- Direction: `{selected['direction']}`",
        f"- Lookback minutes: `{selected['lookback_minutes']}`",
        f"- Quantile: `{selected['quantile']}`",
        f"- Design rank: `{selected['rank_design_total_net_pnl']}`",
        f"- Design trades/wins: `{selected['design_trades']}/{selected['design_wins']}`",
        f"- Design total net pnl: `{float(selected['design_total_net_pnl_bps']):.6f}` bps",
        f"- Holdout trades/wins: `{selected['holdout_trades']}/{selected['holdout_wins']}`",
        f"- Holdout win rate: `{float(selected['holdout_win_rate']):.6f}`",
        f"- Holdout total net pnl: `{float(selected['holdout_total_net_pnl_bps']):.6f}` bps",
        f"- Holdout positive screen: `{bool(selected['holdout_positive_screen'])}`",
        "",
        "## Fixed V55/V57 Rule",
        "",
        f"- Design rank: `{fixed['rank_design_total_net_pnl']}`",
        f"- Design trades/wins: `{fixed['design_trades']}/{fixed['design_wins']}`",
        f"- Design total net pnl: `{float(fixed['design_total_net_pnl_bps']):.6f}` bps",
        f"- Holdout trades/wins: `{fixed['holdout_trades']}/{fixed['holdout_wins']}`",
        f"- Holdout win rate: `{float(fixed['holdout_win_rate']):.6f}`",
        f"- Holdout total net pnl: `{float(fixed['holdout_total_net_pnl_bps']):.6f}` bps",
        f"- Holdout positive screen: `{bool(fixed['holdout_positive_screen'])}`",
        "",
        "## Family Summary",
        "",
        f"- Design positive screen pass count: `{payload['design_positive_screen_pass_count']}`",
        f"- Holdout positive screen pass count: `{payload['holdout_positive_screen_pass_count']}`",
        f"- Both design and holdout positive screen pass count: `{payload['both_positive_screen_pass_count']}`",
        f"- Design-selected is fixed V55/V57 rule: `{payload['design_selected_is_fixed_v55']}`",
        "",
        "## Top 10 By Design Pnl",
        "",
        design_top.to_markdown(index=False),
        "",
        "## Files",
        "",
        f"- Candidate evaluations: `{payload['candidate_evaluations_path']}`",
        f"- Summary JSON: `{payload['summary_path']}`",
        "",
        "## Caveat",
        "",
        "This split still reuses historical folds. It is stronger than full-period ranking, but weaker than genuinely new BTCUSDC data.",
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
                full_summary = summarize_sparse_tp_outcomes(ledger, quote_surcharge_bps=0.5)
                split_summary = summarize_sparse_tp_by_fold_sets(
                    ledger,
                    design_folds=DESIGN_FOLDS,
                    holdout_folds=HOLDOUT_FOLDS,
                    quote_surcharge_bps=0.5,
                )
                rows.append(
                    {
                        "direction": str(direction),
                        "lookback_minutes": int(lookback),
                        "quantile": float(quantile),
                        **full_summary,
                        **split_summary,
                        "full_basic_gate_screen": bool(_basic_gate(full_summary)),
                    }
                )

    evaluations = pd.DataFrame(rows)
    evaluations["design_positive_screen"] = evaluations.apply(lambda row: _prefixed_basic_gate(row, "design"), axis=1)
    evaluations["holdout_positive_screen"] = evaluations.apply(lambda row: _prefixed_basic_gate(row, "holdout"), axis=1)
    evaluations = evaluations.sort_values(
        ["design_total_net_pnl_bps", "design_wins", "design_trades", "holdout_total_net_pnl_bps", "direction", "lookback_minutes", "quantile"],
        ascending=[False, False, False, False, True, True, True],
    ).reset_index(drop=True)
    evaluations["rank_design_total_net_pnl"] = range(1, len(evaluations) + 1)

    eval_path = OUT_DIR / "v60_design_selector_candidate_evaluations.csv"
    evaluations.to_csv(eval_path, index=False)

    design_selected = evaluations.iloc[0].to_dict()
    fixed_mask = (
        (evaluations["direction"] == FIXED_V55["direction"])
        & (evaluations["lookback_minutes"].astype(int) == int(FIXED_V55["lookback_minutes"]))
        & (evaluations["quantile"].astype(float).round(4) == float(FIXED_V55["quantile"]))
    )
    if not fixed_mask.any():
        raise SystemExit("fixed V55/V57 rule missing from V60 evaluations")
    fixed_row = evaluations.loc[fixed_mask].iloc[0].to_dict()

    payload: dict[str, object] = {
        "input_bars": str(INPUT_BARS),
        "bar_rows": int(len(bars)),
        "candidate_evaluations_path": str(eval_path),
        "summary_path": str(OUT_DIR / "v60_summary.json"),
        "total_candidates": int(len(evaluations)),
        "design_selected_rule": design_selected,
        "fixed_v55_rule": fixed_row,
        "design_selected_is_fixed_v55": bool(
            design_selected["direction"] == fixed_row["direction"]
            and int(design_selected["lookback_minutes"]) == int(fixed_row["lookback_minutes"])
            and abs(float(design_selected["quantile"]) - float(fixed_row["quantile"])) < 1e-12
        ),
        "design_positive_screen_pass_count": int(evaluations["design_positive_screen"].astype(bool).sum()),
        "holdout_positive_screen_pass_count": int(evaluations["holdout_positive_screen"].astype(bool).sum()),
        "both_positive_screen_pass_count": int((evaluations["design_positive_screen"].astype(bool) & evaluations["holdout_positive_screen"].astype(bool)).sum()),
    }
    (OUT_DIR / "v60_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload, evaluations.head(10))
    print(json.dumps(payload, indent=2))
