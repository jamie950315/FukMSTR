from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import summarize_static_bucket_viability


ROOT = Path(__file__).resolve().parents[1]
INPUT_LEDGER = ROOT / "runs" / "research_v26_btcusdc_full_public_replay" / "btcusdc_contract_trade_ledger.csv"
OUT_DIR = ROOT / "runs" / "research_v84_btcusdc_exit_lane_bucket_audit"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V84_BTCUSDC_EXIT_LANE_BUCKET_AUDIT_RESULTS.md"

BUCKET_COLUMNS = ("exit_reason", "v24_core_lane", "v24_rescue_lane", "take_profit_bps", "hold_sec", "signal")
OUTCOME_COLUMNS = ("exit_reason",)
MIN_TRADES = 50
MIN_TOTAL_NET_PNL_BPS = 0.0
MIN_POSITIVE_FOLD_RATE = 1.0
MIN_POSITIVE_MONTH_RATE = 1.0
MIN_WIN_RATE = 0.50


def _write_report(payload: dict[str, object], buckets: pd.DataFrame) -> None:
    aggregate = payload["aggregate"]
    lines = [
        "# Research V84 BTCUSDC Exit/Lane Bucket Audit Results",
        "",
        "## Decision",
        "",
        f"- Promote pretrade bucket: `{aggregate['promote_pretrade_bucket']}`",
        f"- Passed pretrade buckets: `{aggregate['passed_pretrade_bucket_count']}`",
        f"- Passed outcome buckets: `{aggregate['passed_outcome_bucket_count']}`",
        "",
        "## Gate",
        "",
        f"- Min trades: `{MIN_TRADES}`",
        f"- Min total net PnL: `{MIN_TOTAL_NET_PNL_BPS}` bps",
        f"- Min positive fold rate: `{MIN_POSITIVE_FOLD_RATE}`",
        f"- Min positive month rate: `{MIN_POSITIVE_MONTH_RATE}`",
        f"- Min win rate: `{MIN_WIN_RATE}`",
        "",
        "## Buckets",
        "",
        buckets.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V84 checks whether the V26 BTCUSDC full public replay has any stable pretrade subset among lane, side, take-profit size, or hold-time fields. It also shows exit_reason as an outcome-only bucket. Outcome buckets can explain losses, but they cannot be used as entry filters because they are only known after the trade exits.",
        "",
        "The take_profit outcome bucket passes because winning take-profit exits are profitable by construction. No pretrade bucket passes. The result does not promote a strategy route and does not support another lane-only or exit-only rescue loop.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    if not INPUT_LEDGER.exists():
        raise SystemExit(f"missing input ledger: {INPUT_LEDGER}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    trades = pd.read_csv(INPUT_LEDGER)
    result = summarize_static_bucket_viability(
        trades,
        bucket_columns=BUCKET_COLUMNS,
        outcome_columns=OUTCOME_COLUMNS,
        min_trades=MIN_TRADES,
        min_total_net_pnl_bps=MIN_TOTAL_NET_PNL_BPS,
        min_positive_fold_rate=MIN_POSITIVE_FOLD_RATE,
        min_positive_month_rate=MIN_POSITIVE_MONTH_RATE,
        min_win_rate=MIN_WIN_RATE,
    )
    buckets = pd.DataFrame(result["buckets"])
    buckets.to_csv(OUT_DIR / "v84_exit_lane_buckets.csv", index=False)
    payload = {
        "version": "v84_btcusdc_exit_lane_bucket_audit",
        "input_ledger": str(INPUT_LEDGER),
        "aggregate": result["aggregate"],
        "outputs": {
            "summary_json": str(OUT_DIR / "v84_summary.json"),
            "exit_lane_buckets": str(OUT_DIR / "v84_exit_lane_buckets.csv"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v84_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, buckets)
    print(json.dumps(payload, indent=2, default=str))
