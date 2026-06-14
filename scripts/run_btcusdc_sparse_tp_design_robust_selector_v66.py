from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_contract_lock import BTCUSDCContractGate, BTCUSDCContractPolicy, _stress_from_v24
from lob_microprice_lab.btcusdc_sparse_tp import (
    SparseTakeProfitPolicy,
    apply_take_profit_exit,
    build_sparse_abs_return_entries,
    shift_sparse_entries_to_delay,
    summarize_boolean_runs,
    summarize_sparse_delay_scan,
    summarize_sparse_tp_outcomes,
)
from run_btcusdc_sparse_tp_dense_delay_scan_v64 import _fast_contract_gate


ROOT = Path(__file__).resolve().parents[1]
INPUT_BARS = ROOT / "runs" / "research_v48_btcusdc_full_1m_direct_ml_input" / "btcusdc_full_1m_bars.csv"
V24_RUN_DIR = ROOT / "runs" / "research_v24_btc_adaptive_exit_safety_lock"
OUT_DIR = ROOT / "runs" / "research_v66_btcusdc_sparse_tp_design_robust_selector"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V66_DESIGN_ROBUST_SELECTOR_RESULTS.md"

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
DELAYS = range(0, 121)
LOOKBACKS = (720, 1080, 1440, 2160, 2880)
QUANTILES = (0.9900, 0.9925, 0.9950, 0.9975, 0.9990)
DIRECTIONS = ("reversal", "momentum")
V60_RULE = {"name": "v60_design_total_selected", "direction": "reversal", "lookback_minutes": 1080, "quantile": 0.9900}


def _load_bars() -> pd.DataFrame:
    bars = pd.read_csv(INPUT_BARS, parse_dates=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        bars[col] = pd.to_numeric(bars[col], errors="coerce")
    bars["replay_date"] = bars["timestamp"].dt.date.astype(str)
    return bars


def _rule_name(rule: dict[str, object]) -> str:
    return f"{rule['direction']}_lb{int(rule['lookback_minutes'])}_q{float(rule['quantile']):.4f}".replace(".", "p")


def _base_entries_for_rule(bars: pd.DataFrame, rule: dict[str, object], fold_set: set[int]) -> pd.DataFrame:
    entries = build_sparse_abs_return_entries(
        bars,
        folds=FOLDS,
        entry_delay_minutes=0,
        lookback_minutes=int(rule["lookback_minutes"]),
        horizon_minutes=1440,
        quantile=float(rule["quantile"]),
        direction=str(rule["direction"]),
    )
    return entries.loc[pd.to_numeric(entries["fold"], errors="coerce").astype(int).isin(fold_set)].reset_index(drop=True)


def _design_delay_scan(bars: pd.DataFrame, rule: dict[str, object]) -> tuple[pd.DataFrame, pd.DataFrame]:
    base_entries = _base_entries_for_rule(bars, rule, DESIGN_FOLDS)
    tp_policy = SparseTakeProfitPolicy(take_profit_bps=80.0, horizon_minutes=1440)
    rows: list[dict[str, object]] = []
    ledgers: list[pd.DataFrame] = []
    for delay in DELAYS:
        entries = shift_sparse_entries_to_delay(base_entries, bars, folds=FOLDS, entry_delay_minutes=int(delay), bars_prepared=True)
        ledger = apply_take_profit_exit(entries, bars, tp_policy, bars_prepared=True)
        if not ledger.empty:
            tagged = ledger.copy()
            tagged.insert(0, "scan_entry_delay_min", int(delay))
            ledgers.append(tagged)
        summary = summarize_sparse_tp_outcomes(ledger, quote_surcharge_bps=0.5)
        screen_passed = bool(summary["trades"] > 0 and summary["wins"] == summary["trades"] and summary["total_net_pnl_bps"] > 0.0)
        rows.append(
            {
                "entry_delay_min": int(delay),
                "entry_count": int(len(entries)),
                "screen_passed": screen_passed,
                "trades": int(summary["trades"]),
                "wins": int(summary["wins"]),
                "win_rate": float(summary["win_rate"]),
                "total_net_pnl_bps": float(summary["total_net_pnl_bps"]),
                "mean_net_pnl_bps": float(summary["mean_net_pnl_bps"]),
                "min_trade_net_pnl_bps": float(summary["min_trade_net_pnl_bps"]),
                "take_profit_rate": float(summary["take_profit_rate"]),
            }
        )
    scan = pd.DataFrame(rows)
    combined = pd.concat(ledgers, ignore_index=True) if ledgers else pd.DataFrame()
    return scan, combined


def _holdout_contract_delay_scan(bars: pd.DataFrame, rule: dict[str, object], *, stress: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    base_entries = _base_entries_for_rule(bars, rule, HOLDOUT_FOLDS)
    tp_policy = SparseTakeProfitPolicy(take_profit_bps=80.0, horizon_minutes=1440)
    policy = BTCUSDCContractPolicy(source_symbol=f"BTCUSDC V66 holdout dense delay {_rule_name(rule)}")
    gate = BTCUSDCContractGate()
    rows: list[dict[str, object]] = []
    ledgers: list[pd.DataFrame] = []
    for delay in DELAYS:
        entries = shift_sparse_entries_to_delay(base_entries, bars, folds=FOLDS, entry_delay_minutes=int(delay), bars_prepared=True)
        ledger = apply_take_profit_exit(entries, bars, tp_policy, bars_prepared=True)
        if not ledger.empty:
            tagged = ledger.copy()
            tagged.insert(0, "scan_entry_delay_min", int(delay))
            ledgers.append(tagged)
        gate_summary = _fast_contract_gate(ledger, stress=stress, policy=policy, gate=gate)
        rows.append(
            {
                "entry_delay_min": int(delay),
                "entry_count": int(len(entries)),
                **gate_summary,
                "failed_checks": ";".join(gate_summary["failed_checks"]),
            }
        )
    scan = pd.DataFrame(rows)
    combined = pd.concat(ledgers, ignore_index=True) if ledgers else pd.DataFrame()
    return scan, combined


def _write_report(payload: dict[str, object], design_top: pd.DataFrame, holdout_ranges: pd.DataFrame, holdout_worst: pd.DataFrame) -> None:
    selected = payload["design_robust_selected_rule"]
    lines = [
        "# Research V66 Design-Robust Selector Results",
        "",
        "## Purpose",
        "",
        "V66 ranks the V59 parameter neighborhood by dense entry-delay robustness on design folds only, then evaluates the selected candidate on holdout folds.",
        "",
        "The TP80 exit, no-stop policy, V26 contract gate settings, and V59 parameter grid are unchanged.",
        "",
        "## Design-Robust Selected Candidate",
        "",
        f"- Direction: `{selected['direction']}`",
        f"- Lookback minutes: `{selected['lookback_minutes']}`",
        f"- Quantile: `{selected['quantile']}`",
        f"- Design pass count: `{selected['pass_count']}/{selected['delay_count']}`",
        f"- Design fail ranges: `{selected['fail_delay_ranges']}`",
        f"- Design min total net pnl: `{float(selected['min_total_net_pnl_bps']):.6f}` bps",
        f"- Same as V60 design-total candidate: `{payload['selected_same_as_v60']}`",
        "",
        "## Holdout Dense Gate Result For Design-Robust Candidate",
        "",
        f"- Holdout gate pass count: `{payload['selected_holdout_pass_count']}/{payload['delay_count']}`",
        f"- Holdout fail ranges: `{payload['selected_holdout_fail_ranges']}`",
        f"- Worst holdout delay: `{payload['selected_holdout_worst_delay']}`",
        f"- Worst holdout account return: `{float(payload['selected_holdout_worst_account_return_pct']):.6f}%`",
        "",
        "## V60 Candidate Holdout Reference",
        "",
        f"- V60 holdout gate pass count: `{payload['v60_holdout_pass_count']}/{payload['delay_count']}`",
        f"- V60 holdout fail ranges: `{payload['v60_holdout_fail_ranges']}`",
        "",
        "## Top 10 Design-Robust Candidates",
        "",
        design_top.to_markdown(index=False),
        "",
        "## Selected Holdout Pass/Fail Ranges",
        "",
        holdout_ranges.to_markdown(index=False),
        "",
        "## Selected Holdout Worst 10 Delays",
        "",
        holdout_worst.to_markdown(index=False),
        "",
        "## Files",
        "",
        f"- Design candidate robustness CSV: `{payload['design_candidate_csv']}`",
        f"- Selected holdout delay scan CSV: `{payload['selected_holdout_scan_csv']}`",
        f"- V60 holdout delay scan CSV: `{payload['v60_holdout_scan_csv']}`",
        f"- Summary JSON: `{payload['summary_json']}`",
        "",
        "## Caveat",
        "",
        "This avoids selecting on holdout, but it is still historical BTCUSDC data and not future unseen validation.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    bars = _load_bars()

    candidate_rows: list[dict[str, object]] = []
    for direction in DIRECTIONS:
        for lookback in LOOKBACKS:
            for quantile in QUANTILES:
                rule = {"direction": direction, "lookback_minutes": int(lookback), "quantile": float(quantile)}
                scan, _ = _design_delay_scan(bars, rule)
                delay_summary = summarize_sparse_delay_scan(
                    scan,
                    pass_col="screen_passed",
                    total_col="total_net_pnl_bps",
                    min_trade_col="min_trade_net_pnl_bps",
                )
                candidate_rows.append(
                    {
                        **rule,
                        "rule_name": _rule_name(rule),
                        "design_base_entry_count": int(scan["entry_count"].max()) if not scan.empty else 0,
                        **delay_summary,
                    }
                )

    candidates = pd.DataFrame(candidate_rows).sort_values(
        ["pass_count", "min_total_net_pnl_bps", "mean_total_net_pnl_bps", "design_base_entry_count", "direction", "lookback_minutes", "quantile"],
        ascending=[False, False, False, False, True, True, True],
    ).reset_index(drop=True)
    candidates["rank_design_delay_robust"] = range(1, len(candidates) + 1)
    candidates_path = OUT_DIR / "v66_design_delay_robust_candidate_rankings.csv"
    candidates.to_csv(candidates_path, index=False)

    selected = candidates.iloc[0].to_dict()
    selected_rule = {
        "name": "v66_design_delay_robust_selected",
        "direction": selected["direction"],
        "lookback_minutes": int(selected["lookback_minutes"]),
        "quantile": float(selected["quantile"]),
    }

    stress = _stress_from_v24(V24_RUN_DIR, BTCUSDCContractPolicy())
    selected_holdout, selected_ledger = _holdout_contract_delay_scan(bars, selected_rule, stress=stress)
    selected_holdout_path = OUT_DIR / "v66_selected_holdout_dense_delay_contract_gate_summary.csv"
    selected_holdout.to_csv(selected_holdout_path, index=False)
    selected_ledger.to_csv(OUT_DIR / "v66_selected_holdout_dense_delay_combined_tp80_ledger.csv", index=False)
    selected_ranges = summarize_boolean_runs(selected_holdout, value_col="gate_passed", index_col="entry_delay_min")
    selected_ranges_path = OUT_DIR / "v66_selected_holdout_pass_fail_ranges.csv"
    selected_ranges.to_csv(selected_ranges_path, index=False)
    selected_worst = selected_holdout.sort_values(["account_return_pct", "total_bps", "entry_delay_min"], ascending=[True, True, True]).head(10)
    selected_worst.to_csv(OUT_DIR / "v66_selected_holdout_worst10.csv", index=False)

    v60_holdout, v60_ledger = _holdout_contract_delay_scan(bars, V60_RULE, stress=stress)
    v60_holdout_path = OUT_DIR / "v66_v60_reference_holdout_dense_delay_contract_gate_summary.csv"
    v60_holdout.to_csv(v60_holdout_path, index=False)
    v60_ledger.to_csv(OUT_DIR / "v66_v60_reference_holdout_dense_delay_combined_tp80_ledger.csv", index=False)
    v60_ranges = summarize_boolean_runs(v60_holdout, value_col="gate_passed", index_col="entry_delay_min")
    v60_ranges.to_csv(OUT_DIR / "v66_v60_reference_holdout_pass_fail_ranges.csv", index=False)

    selected_delay_summary = summarize_sparse_delay_scan(
        selected_holdout.rename(columns={"total_bps": "total_net_pnl_bps", "min_trade_bps": "min_trade_net_pnl_bps"}),
        pass_col="gate_passed",
        total_col="total_net_pnl_bps",
        min_trade_col="min_trade_net_pnl_bps",
    )
    v60_delay_summary = summarize_sparse_delay_scan(
        v60_holdout.rename(columns={"total_bps": "total_net_pnl_bps", "min_trade_bps": "min_trade_net_pnl_bps"}),
        pass_col="gate_passed",
        total_col="total_net_pnl_bps",
        min_trade_col="min_trade_net_pnl_bps",
    )

    same_as_v60 = (
        selected_rule["direction"] == V60_RULE["direction"]
        and int(selected_rule["lookback_minutes"]) == int(V60_RULE["lookback_minutes"])
        and abs(float(selected_rule["quantile"]) - float(V60_RULE["quantile"])) < 1e-12
    )
    payload: dict[str, object] = {
        "input_bars": str(INPUT_BARS),
        "bar_rows": int(len(bars)),
        "design_folds": sorted(DESIGN_FOLDS),
        "holdout_folds": sorted(HOLDOUT_FOLDS),
        "delay_count": int(len(DELAYS)),
        "design_robust_selected_rule": selected,
        "selected_same_as_v60": bool(same_as_v60),
        "selected_holdout_pass_count": int(selected_delay_summary["pass_count"]),
        "selected_holdout_fail_ranges": str(selected_delay_summary["fail_delay_ranges"]),
        "selected_holdout_worst_delay": selected_delay_summary["worst_delay"],
        "selected_holdout_worst_account_return_pct": float(selected_worst.iloc[0]["account_return_pct"]) if not selected_worst.empty else 0.0,
        "v60_holdout_pass_count": int(v60_delay_summary["pass_count"]),
        "v60_holdout_fail_ranges": str(v60_delay_summary["fail_delay_ranges"]),
        "design_candidate_csv": str(candidates_path),
        "selected_holdout_scan_csv": str(selected_holdout_path),
        "selected_holdout_ranges_csv": str(selected_ranges_path),
        "v60_holdout_scan_csv": str(v60_holdout_path),
        "summary_json": str(OUT_DIR / "v66_summary.json"),
    }
    (OUT_DIR / "v66_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, candidates.head(10), selected_ranges, selected_worst)
    print(json.dumps(payload, indent=2, default=str))
