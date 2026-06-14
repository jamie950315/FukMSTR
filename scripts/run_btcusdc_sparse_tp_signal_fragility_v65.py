from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_sparse_tp import summarize_sparse_delay_signal_fragility


ROOT = Path(__file__).resolve().parents[1]
V64_DIR = ROOT / "runs" / "research_v64_btcusdc_sparse_tp_dense_delay_scan"
V64_LEDGER = V64_DIR / "v64_dense_delay_combined_tp80_ledger.csv"
V64_SUMMARY = V64_DIR / "v64_dense_delay_contract_gate_summary.csv"
OUT_DIR = ROOT / "runs" / "research_v65_btcusdc_sparse_tp_signal_fragility_audit"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V65_SIGNAL_FRAGILITY_AUDIT_RESULTS.md"


def _load_v64() -> tuple[pd.DataFrame, pd.DataFrame]:
    ledger = pd.read_csv(V64_LEDGER, parse_dates=["signal_timestamp", "timestamp", "exit_timestamp"])
    summary = pd.read_csv(V64_SUMMARY)
    return ledger, summary


def _failed_delay_losses(ledger: pd.DataFrame, summary: pd.DataFrame) -> pd.DataFrame:
    failed_delays = set(summary.loc[~summary["gate_passed"].astype(bool), "entry_delay_min"].astype(int))
    out = ledger.copy()
    out["scan_entry_delay_min"] = pd.to_numeric(out["scan_entry_delay_min"], errors="coerce").astype(int)
    out["final_net_pnl_bps"] = pd.to_numeric(out["net_pnl_bps"], errors="coerce").fillna(0.0) - 0.5
    out = out.loc[out["scan_entry_delay_min"].isin(failed_delays) & (out["final_net_pnl_bps"] <= 0.0)].copy()
    keep_cols = [
        "scan_entry_delay_min",
        "fold",
        "signal_idx",
        "signal_timestamp",
        "timestamp",
        "signal",
        "entry_px",
        "exit_timestamp",
        "exit_reason",
        "exit_px",
        "net_pnl_bps",
        "final_net_pnl_bps",
        "hold_sec",
    ]
    return out[keep_cols].sort_values(["scan_entry_delay_min", "fold", "signal_idx"]).reset_index(drop=True)


def _write_report(payload: dict[str, object], signal_fragility: pd.DataFrame, failed_delay_losses: pd.DataFrame) -> None:
    lines = [
        "# Research V65 Signal Fragility Audit Results",
        "",
        "## Purpose",
        "",
        "V65 traces the V64 dense delay failures back to individual holdout signals.",
        "",
        "No rule, threshold, or gate setting is changed. This is an attribution audit over the V64 0..120 minute delay scan.",
        "",
        "## Summary",
        "",
        f"- Signals audited: `{payload['signal_count']}`",
        f"- Signals with at least one loss after surcharge: `{payload['signals_with_loss_count']}`",
        f"- Total losing signal-delay rows: `{payload['total_losing_signal_delay_rows']}`",
        f"- Failed V64 delays: `{payload['failed_delay_count']}`",
        f"- Failed-delay losing rows: `{payload['failed_delay_losing_rows']}`",
        "",
        "## Most Fragile Signals",
        "",
        signal_fragility.head(10).to_markdown(index=False),
        "",
        "## Failed Delay Loss Attribution",
        "",
        failed_delay_losses.to_markdown(index=False),
        "",
        "## Files",
        "",
        f"- Signal fragility CSV: `{payload['signal_fragility_csv']}`",
        f"- Failed delay losses CSV: `{payload['failed_delay_losses_csv']}`",
        f"- Summary JSON: `{payload['summary_json']}`",
        "",
        "## Caveat",
        "",
        "This audit explains which historical signals create delay fragility. It does not make the rule future-validated.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ledger, summary = _load_v64()

    signal_fragility = summarize_sparse_delay_signal_fragility(ledger, quote_surcharge_bps=0.5)
    signal_fragility_path = OUT_DIR / "v65_signal_delay_fragility.csv"
    signal_fragility.to_csv(signal_fragility_path, index=False)

    failed_losses = _failed_delay_losses(ledger, summary)
    failed_losses_path = OUT_DIR / "v65_failed_delay_losing_trades.csv"
    failed_losses.to_csv(failed_losses_path, index=False)

    signals_with_loss = signal_fragility.loc[pd.to_numeric(signal_fragility["loss_delay_count"], errors="coerce") > 0]
    failed_delays = summary.loc[~summary["gate_passed"].astype(bool)].copy()
    payload: dict[str, object] = {
        "v64_ledger": str(V64_LEDGER),
        "v64_summary": str(V64_SUMMARY),
        "signal_count": int(len(signal_fragility)),
        "signals_with_loss_count": int(len(signals_with_loss)),
        "total_losing_signal_delay_rows": int(pd.to_numeric(signal_fragility["loss_delay_count"], errors="coerce").fillna(0).sum()),
        "failed_delay_count": int(len(failed_delays)),
        "failed_delay_losing_rows": int(len(failed_losses)),
        "top_fragile_signal": signal_fragility.iloc[0].to_dict() if not signal_fragility.empty else {},
        "failed_delays": failed_delays["entry_delay_min"].astype(int).tolist(),
        "signal_fragility_csv": str(signal_fragility_path),
        "failed_delay_losses_csv": str(failed_losses_path),
        "summary_json": str(OUT_DIR / "v65_summary.json"),
    }
    (OUT_DIR / "v65_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, signal_fragility, failed_losses)
    print(json.dumps(payload, indent=2, default=str))
