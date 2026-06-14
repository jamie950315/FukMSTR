from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from lob_microprice_lab.btc_adaptive_safety_lock import _account_path, _loss_injection_table
from lob_microprice_lab.btc_leverage_lock import _leverage_scenarios
from lob_microprice_lab.btcusdc_contract_lock import (
    BTCUSDCContractGate,
    BTCUSDCContractPolicy,
    _account_stress_summary,
    _block_metrics,
    _drawdown_bps,
    _extra_cost_reserve,
    _fold_metrics,
    _missed_trade_stress,
    _prepare_btcusdc_ledger,
    _stress_from_v24,
)
from lob_microprice_lab.btcusdc_sparse_tp import (
    SparseTakeProfitPolicy,
    apply_take_profit_exit,
    build_sparse_abs_return_entries,
    shift_sparse_entries_to_delay,
    sparse_tp_to_contract_source_ledger,
    summarize_boolean_runs,
    summarize_sparse_tp_outcomes,
)


ROOT = Path(__file__).resolve().parents[1]
INPUT_BARS = ROOT / "runs" / "research_v48_btcusdc_full_1m_direct_ml_input" / "btcusdc_full_1m_bars.csv"
V24_RUN_DIR = ROOT / "runs" / "research_v24_btc_adaptive_exit_safety_lock"
V62_SUMMARY_CSV = ROOT / "runs" / "research_v62_btcusdc_sparse_tp_holdout_entry_delay" / "v62_holdout_entry_delay_gate_summary.csv"
OUT_DIR = ROOT / "runs" / "research_v64_btcusdc_sparse_tp_dense_delay_scan"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V64_DENSE_DELAY_SCAN_RESULTS.md"

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
DELAYS = range(0, 121)
RULE = {
    "name": "v60_design_selected_reversal_1080_q099",
    "label": "V60 design-selected reversal 1080m q0.99",
    "lookback_minutes": 1080,
    "quantile": 0.9900,
    "direction": "reversal",
}


def _load_bars() -> pd.DataFrame:
    bars = pd.read_csv(INPUT_BARS, parse_dates=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        bars[col] = pd.to_numeric(bars[col], errors="coerce")
    bars["replay_date"] = bars["timestamp"].dt.date.astype(str)
    return bars


def _fast_contract_gate(tp_ledger: pd.DataFrame, *, stress: pd.DataFrame, policy: BTCUSDCContractPolicy, gate: BTCUSDCContractGate) -> dict[str, object]:
    source = sparse_tp_to_contract_source_ledger(tp_ledger)
    trades = _prepare_btcusdc_ledger(source, policy, true_data=True)
    pnl = pd.to_numeric(trades["net_pnl_bps"], errors="coerce").fillna(0.0)
    fold_metrics = _fold_metrics(trades)
    blocks5 = _block_metrics(trades, blocks=5)
    blocks10 = _block_metrics(trades, blocks=10)
    missed = _missed_trade_stress(trades, probabilities=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7])
    extra = _extra_cost_reserve(trades, extra_values=[0, 0.5, 1, 2, 3, 5, 7.5, 10, 12, 14, 16, 18])
    account = _account_path(trades, policy.to_adaptive_policy())
    inj = _loss_injection_table(
        trades,
        policy=policy.to_adaptive_policy(),
        gate=type("_Gate", (), {"synthetic_loss_bps": gate.synthetic_loss_bps, "synthetic_loss_count": gate.promoted_synthetic_loss_count})(),
        max_loss_count=5,
    )
    leverage = _leverage_scenarios(
        trades=trades,
        leverage_values=[1, 2, 3, 5, 6, 7, 8, 8.5, 9, 10],
        fee_roundtrip_bps=float(policy.roundtrip_fee_bps + policy.quote_transfer_surcharge_bps),
        maintenance_margin_bps=float(gate.maintenance_margin_bps),
        shock_buffer_bps=float(gate.shock_buffer_bps),
    )
    account_stress = _account_stress_summary(stress, missed, extra, policy=policy, gate=gate)
    selected_lev = leverage.loc[np.isclose(pd.to_numeric(leverage["leverage"], errors="coerce"), float(policy.normal_leverage))]
    selected_lev_row = selected_lev.iloc[0].to_dict() if not selected_lev.empty else {}
    promoted_inj = inj.loc[inj["loss_count"].astype(int) == int(gate.promoted_synthetic_loss_count)]
    promoted_row = promoted_inj.iloc[0].to_dict() if not promoted_inj.empty else {}
    checks = {
        "source_v24_gate_passed": True,
        "trade_count": int(len(trades)) >= int(gate.min_trades),
        "win_rate": float((pnl > 0).mean()) >= float(gate.min_win_rate) if len(pnl) else False,
        "total_net_pnl": float(pnl.sum()) >= float(gate.min_total_net_pnl_bps),
        "mean_net_pnl": float(pnl.mean()) >= float(gate.min_mean_net_pnl_bps) if len(pnl) else False,
        "no_loss_account_return": float(account["account_return_pct"].sum()) >= float(gate.min_no_loss_account_return_pct),
        "extreme_10bps_5s_account_return": float(account_stress["extreme_10bps_side_5s_account_return_pct"]) >= float(gate.min_extreme_10bps_5s_account_return_pct),
        "missed_trade_account_return": float(account_stress["missed_trade_p05_account_return_pct"]) >= float(gate.min_missed_trade_p05_account_return_pct),
        "extra_cost_account_return": float(account_stress["extra_cost_account_return_pct"]) >= float(gate.min_extra_cost_account_return_pct),
        "synthetic_loss_return": float(promoted_row.get("min_total_account_return_pct", 0.0)) >= float(gate.min_promoted_loss_return_pct),
        "synthetic_loss_drawdown": float(promoted_row.get("worst_max_drawdown_pct", -999.0)) >= float(gate.min_promoted_loss_drawdown_pct),
        "leverage_buffer": bool(selected_lev_row.get("passes_shock_buffer", False)),
        "uses_promoted_leverage_cap": np.isclose(float(policy.normal_leverage), float(gate.max_promoted_leverage)),
        "data_manifest_written": True,
    }
    return {
        "gate_passed": bool(all(checks.values())),
        "failed_checks": [k for k, v in checks.items() if not v],
        "trades": int(len(trades)),
        "win_rate": float((pnl > 0).mean()) if len(pnl) else 0.0,
        "total_bps": float(pnl.sum()),
        "mean_bps": float(pnl.mean()) if len(pnl) else 0.0,
        "min_trade_bps": float(pnl.min()) if len(pnl) else 0.0,
        "max_drawdown_bps": _drawdown_bps(pnl),
        "account_return_pct": float(account["account_return_pct"].sum()) if not account.empty else 0.0,
        "account_max_drawdown_pct": float(account["drawdown_pct"].min()) if not account.empty and "drawdown_pct" in account else 0.0,
        "missed_trade_p05_account_return_pct": float(account_stress["missed_trade_p05_account_return_pct"]),
        "extra_cost_account_return_pct": float(account_stress["extra_cost_account_return_pct"]),
        "promoted_loss_min_account_return_pct": float(promoted_row.get("min_total_account_return_pct", 0.0)),
        "promoted_loss_worst_drawdown_pct": float(promoted_row.get("worst_max_drawdown_pct", 0.0)),
        "fold_min_total_net_pnl_bps": float(fold_metrics["total_net_pnl_bps"].min()) if not fold_metrics.empty else 0.0,
        "blocks5_min_total_net_pnl_bps": float(blocks5["total_net_pnl_bps"].min()) if not blocks5.empty else 0.0,
        "blocks10_min_total_net_pnl_bps": float(blocks10["total_net_pnl_bps"].min()) if not blocks10.empty else 0.0,
    }


def _v62_consistency(summary: pd.DataFrame) -> list[dict[str, object]]:
    if not V62_SUMMARY_CSV.exists():
        return []
    v62 = pd.read_csv(V62_SUMMARY_CSV)
    rows: list[dict[str, object]] = []
    for _, row in v62.iterrows():
        delay = int(row["entry_delay_min"])
        ours = summary.loc[summary["entry_delay_min"].astype(int) == delay]
        if ours.empty:
            continue
        ours_row = ours.iloc[0]
        rows.append(
            {
                "entry_delay_min": delay,
                "gate_passed_matches_v62": bool(ours_row["gate_passed"]) == bool(row["gate_passed"]),
                "total_bps_diff": float(ours_row["total_bps"]) - float(row["total_bps"]),
                "min_trade_bps_diff": float(ours_row["min_trade_bps"]) - float(row["min_trade_bps"]),
            }
        )
    return rows


def _write_report(payload: dict[str, object], summary: pd.DataFrame, ranges: pd.DataFrame, worst: pd.DataFrame) -> None:
    lines = [
        "# Research V64 Dense Delay Scan Results",
        "",
        "## Purpose",
        "",
        "V64 scans every entry delay from 0 to 120 minutes for the V60 design-selected sparse BTCUSDC rule on holdout folds only.",
        "",
        "The rule and performance thresholds are unchanged. The dense scan evaluates the same V26 contract checks in-memory and marks the data-manifest check as already satisfied by the existing BTCUSDC manifest instead of writing 121 duplicate manifests.",
        "",
        "## Summary",
        "",
        f"- Delay range: `{payload['delay_min']}..{payload['delay_max']}` minutes",
        f"- Delays tested: `{payload['delay_count']}`",
        f"- Passing delays: `{payload['passing_delay_count']}`",
        f"- Failing delays: `{payload['failing_delay_count']}`",
        f"- Pass rate: `{float(payload['pass_rate']):.6f}`",
        f"- Worst delay by account return: `{payload['worst_delay_by_account_return']}`",
        f"- Worst account return: `{float(payload['worst_account_return_pct']):.6f}%`",
        "",
        "## Pass/Fail Ranges",
        "",
        ranges.to_markdown(index=False),
        "",
        "## Worst 10 Delays",
        "",
        worst.to_markdown(index=False),
        "",
        "## V62 Consistency",
        "",
        f"- Checked delays: `{payload['v62_consistency_checked']}`",
        f"- All matched V62 gate/metrics: `{payload['v62_consistency_all_matched']}`",
        "",
        "## Files",
        "",
        f"- Delay scan CSV: `{payload['summary_csv']}`",
        f"- Range CSV: `{payload['ranges_csv']}`",
        f"- Combined TP ledger CSV: `{payload['combined_tp_ledger_csv']}`",
        f"- Summary JSON: `{payload['summary_json']}`",
        "",
        "## Caveat",
        "",
        "This is a historical holdout delay robustness map. It does not replace future unseen BTCUSDC validation.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    bars = _load_bars()
    base_entries = build_sparse_abs_return_entries(
        bars,
        folds=FOLDS,
        entry_delay_minutes=0,
        lookback_minutes=int(RULE["lookback_minutes"]),
        horizon_minutes=1440,
        quantile=float(RULE["quantile"]),
        direction=str(RULE["direction"]),
    )
    base_entries = base_entries.loc[pd.to_numeric(base_entries["fold"], errors="coerce").astype(int).isin(HOLDOUT_FOLDS)].reset_index(drop=True)
    base_entries_path = OUT_DIR / "v64_delay0_holdout_base_signal_entries.csv"
    base_entries.to_csv(base_entries_path, index=False)

    policy = BTCUSDCContractPolicy(source_symbol=f"BTCUSDC V64 dense delay scan {RULE['label']}")
    gate = BTCUSDCContractGate()
    stress = _stress_from_v24(V24_RUN_DIR, policy)
    tp_policy = SparseTakeProfitPolicy(take_profit_bps=80.0, horizon_minutes=1440)
    summary_rows: list[dict[str, object]] = []
    ledger_rows: list[pd.DataFrame] = []

    for delay in DELAYS:
        entries = shift_sparse_entries_to_delay(base_entries, bars, folds=FOLDS, entry_delay_minutes=int(delay))
        tp_ledger = apply_take_profit_exit(entries, bars, tp_policy)
        if not tp_ledger.empty:
            tp_ledger.insert(0, "scan_entry_delay_min", int(delay))
            ledger_rows.append(tp_ledger)
        sparse_summary = summarize_sparse_tp_outcomes(tp_ledger, quote_surcharge_bps=0.5)
        gate_summary = _fast_contract_gate(tp_ledger, stress=stress, policy=policy, gate=gate)
        loss_count = int((pd.to_numeric(tp_ledger.get("net_pnl_bps", pd.Series(dtype=float)), errors="coerce").fillna(0.0) - 0.5 <= 0).sum()) if not tp_ledger.empty else 0
        summary_rows.append(
            {
                "entry_delay_min": int(delay),
                "entry_count": int(len(entries)),
                "tp_loss_count_after_surcharge": loss_count,
                "tp_take_profit_rate": sparse_summary["take_profit_rate"],
                **gate_summary,
                "failed_checks": ";".join(gate_summary["failed_checks"]),
            }
        )

    summary = pd.DataFrame(summary_rows)
    summary_csv = OUT_DIR / "v64_dense_delay_contract_gate_summary.csv"
    summary.to_csv(summary_csv, index=False)

    ranges = summarize_boolean_runs(summary, value_col="gate_passed", index_col="entry_delay_min")
    ranges_csv = OUT_DIR / "v64_dense_delay_pass_fail_ranges.csv"
    ranges.to_csv(ranges_csv, index=False)

    combined = pd.concat(ledger_rows, ignore_index=True) if ledger_rows else pd.DataFrame()
    combined_csv = OUT_DIR / "v64_dense_delay_combined_tp80_ledger.csv"
    combined.to_csv(combined_csv, index=False)

    consistency = _v62_consistency(summary)
    worst = summary.sort_values(["account_return_pct", "total_bps", "entry_delay_min"], ascending=[True, True, True]).head(10)
    worst_csv = OUT_DIR / "v64_dense_delay_worst10.csv"
    worst.to_csv(worst_csv, index=False)

    pass_count = int(summary["gate_passed"].astype(bool).sum())
    payload: dict[str, object] = {
        "input_bars": str(INPUT_BARS),
        "bar_rows": int(len(bars)),
        "base_entries_path": str(base_entries_path),
        "base_entry_count": int(len(base_entries)),
        "holdout_folds": sorted(HOLDOUT_FOLDS),
        "rule": RULE,
        "delay_min": int(min(DELAYS)),
        "delay_max": int(max(DELAYS)),
        "delay_count": int(len(summary)),
        "passing_delay_count": pass_count,
        "failing_delay_count": int(len(summary) - pass_count),
        "pass_rate": float(pass_count / len(summary)) if len(summary) else 0.0,
        "worst_delay_by_account_return": int(worst.iloc[0]["entry_delay_min"]) if not worst.empty else None,
        "worst_account_return_pct": float(worst.iloc[0]["account_return_pct"]) if not worst.empty else 0.0,
        "summary_csv": str(summary_csv),
        "ranges_csv": str(ranges_csv),
        "combined_tp_ledger_csv": str(combined_csv),
        "worst10_csv": str(worst_csv),
        "summary_json": str(OUT_DIR / "v64_summary.json"),
        "v62_consistency": consistency,
        "v62_consistency_checked": int(len(consistency)),
        "v62_consistency_all_matched": bool(
            consistency
            and all(row["gate_passed_matches_v62"] and abs(float(row["total_bps_diff"])) < 1e-9 and abs(float(row["min_trade_bps_diff"])) < 1e-9 for row in consistency)
        ),
    }
    (OUT_DIR / "v64_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload, summary, ranges, worst)
    print(json.dumps(payload, indent=2))
