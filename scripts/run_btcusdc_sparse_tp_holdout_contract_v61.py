from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_contract_lock import BTCUSDCContractPolicy, run_btcusdc_contract_lock
from lob_microprice_lab.btcusdc_sparse_tp import (
    SparseTakeProfitPolicy,
    apply_take_profit_exit,
    build_sparse_abs_return_entries,
    sparse_tp_to_contract_source_ledger,
    summarize_sparse_tp_outcomes,
)


ROOT = Path(__file__).resolve().parents[1]
INPUT_BARS = ROOT / "runs" / "research_v48_btcusdc_full_1m_direct_ml_input" / "btcusdc_full_1m_bars.csv"
OUT_DIR = ROOT / "runs" / "research_v61_btcusdc_sparse_tp_holdout_contract"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V61_HOLDOUT_CONTRACT_GATE_RESULTS.md"

FOLDS = (
    (1, "2024-01-05", "2025-04-04", "2025-04-04", "2025-06-03"),
    (2, "2024-03-05", "2025-06-03", "2025-06-03", "2025-08-02"),
    (3, "2024-05-04", "2025-08-02", "2025-08-02", "2025-10-01"),
    (4, "2024-07-03", "2025-10-01", "2025-10-01", "2025-11-30"),
    (5, "2024-09-01", "2025-11-30", "2025-11-30", "2026-01-29"),
    (6, "2024-10-31", "2026-01-29", "2026-01-29", "2026-03-30"),
    (7, "2024-12-30", "2026-03-30", "2026-03-30", "2026-05-29"),
)

HOLDOUT_FOLDS = {5, 6, 7}
RULES = (
    {
        "name": "v60_design_selected_reversal_1080_q099",
        "label": "V60 design-selected reversal 1080m q0.99",
        "lookback_minutes": 1080,
        "quantile": 0.9900,
        "direction": "reversal",
    },
    {
        "name": "fixed_v55_v57_reversal_1440_q0995",
        "label": "Fixed V55/V57 reversal 1440m q0.995",
        "lookback_minutes": 1440,
        "quantile": 0.9950,
        "direction": "reversal",
    },
)


def _load_bars() -> pd.DataFrame:
    bars = pd.read_csv(INPUT_BARS, parse_dates=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    for col in ["open", "high", "low", "close", "volume"]:
        bars[col] = pd.to_numeric(bars[col], errors="coerce")
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars["replay_date"] = bars["timestamp"].dt.date.astype(str)
    return bars


def _evaluate_rule(bars: pd.DataFrame, rule: dict[str, object]) -> dict[str, object]:
    entries = build_sparse_abs_return_entries(
        bars,
        folds=FOLDS,
        entry_delay_minutes=1,
        lookback_minutes=int(rule["lookback_minutes"]),
        horizon_minutes=1440,
        quantile=float(rule["quantile"]),
        direction=str(rule["direction"]),
    )
    entries = entries.loc[pd.to_numeric(entries["fold"], errors="coerce").astype(int).isin(HOLDOUT_FOLDS)].reset_index(drop=True)
    entries_path = OUT_DIR / f"v61_{rule['name']}_holdout_entries.csv"
    entries.to_csv(entries_path, index=False)

    tp_ledger = apply_take_profit_exit(entries, bars, SparseTakeProfitPolicy(take_profit_bps=80.0, horizon_minutes=1440))
    tp_path = OUT_DIR / f"v61_{rule['name']}_holdout_tp80_ledger.csv"
    tp_ledger.to_csv(tp_path, index=False)

    source = sparse_tp_to_contract_source_ledger(tp_ledger)
    source_path = OUT_DIR / f"v61_{rule['name']}_holdout_source_ledger_for_contract_gate.csv"
    source.to_csv(source_path, index=False)

    gate_dir = ROOT / f"runs/research_v61_{rule['name']}_holdout_contract_gate"
    gate = run_btcusdc_contract_lock(
        v24_run_dir=ROOT / "runs" / "research_v24_btc_adaptive_exit_safety_lock",
        out_dir=gate_dir,
        policy=BTCUSDCContractPolicy(source_symbol=f"BTCUSDC V61 holdout-only {rule['label']} ledger"),
        btcusdc_ledger=source_path,
        data_start="2024-01-04",
        data_end="2026-06-10",
        clean=True,
    )

    return {
        **rule,
        "entries_path": str(entries_path),
        "tp_ledger_path": str(tp_path),
        "source_ledger_path": str(source_path),
        "gate_dir": str(gate_dir),
        "summary": summarize_sparse_tp_outcomes(tp_ledger, quote_surcharge_bps=0.5),
        "gate_aggregate": gate["aggregate"],
    }


def _write_report(payload: dict[str, object]) -> None:
    lines = [
        "# Research V61 Holdout Contract Gate Results",
        "",
        "## Purpose",
        "",
        "V61 sends holdout-only sparse BTCUSDC ledgers through the unchanged V26 contract gate.",
        "",
        "The main test is the V60 design-selected rule, selected using folds 1-4 only and evaluated here only on folds 5-7.",
        "",
        "## Results",
        "",
    ]
    for result in payload["results"]:
        gate = result["gate_aggregate"]["gate"]
        summary = result["summary"]
        lines.extend(
            [
                f"### {result['label']}",
                "",
                f"- Gate passed: `{bool(gate['passed'])}`",
                f"- Failed checks: `{';'.join(gate['failed_checks']) if gate['failed_checks'] else ''}`",
                f"- Holdout trades: `{summary['trades']}`",
                f"- Holdout wins: `{summary['wins']}`",
                f"- Holdout win rate: `{float(summary['win_rate']):.6f}`",
                f"- Holdout total net pnl: `{float(summary['total_net_pnl_bps']):.6f}` bps",
                f"- Holdout min trade net pnl: `{float(summary['min_trade_net_pnl_bps']):.6f}` bps",
                f"- Contract account return: `{float(result['gate_aggregate']['account_return_pct_no_compounding']):.6f}%`",
                "",
            ]
        )
    lines.extend(
        [
            "## Files",
            "",
            f"- Summary JSON: `{payload['summary_path']}`",
            "",
        ]
    )
    for result in payload["results"]:
        lines.extend(
            [
                f"- {result['name']} entries: `{result['entries_path']}`",
                f"- {result['name']} contract source ledger: `{result['source_ledger_path']}`",
                f"- {result['name']} gate directory: `{result['gate_dir']}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Caveat",
            "",
            "This is out-of-design relative to the V60 selector split, but it is still historical BTCUSDC data. It is not a substitute for future unseen data.",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    bars = _load_bars()
    results = [_evaluate_rule(bars, rule) for rule in RULES]
    payload: dict[str, object] = {
        "input_bars": str(INPUT_BARS),
        "bar_rows": int(len(bars)),
        "holdout_folds": sorted(HOLDOUT_FOLDS),
        "results": results,
        "summary_path": str(OUT_DIR / "v61_summary.json"),
    }
    (OUT_DIR / "v61_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload)
    print(json.dumps(payload, indent=2))
