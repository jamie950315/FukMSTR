from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import summarize_signal_inversion_viability


ROOT = Path(__file__).resolve().parents[1]
INPUT_LEDGER = ROOT / "runs" / "research_v26_btcusdc_full_public_replay" / "btcusdc_contract_trade_ledger.csv"
OUT_DIR = ROOT / "runs" / "research_v82_btcusdc_signal_inversion_audit"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V82_BTCUSDC_SIGNAL_INVERSION_AUDIT_RESULTS.md"

MIN_TOTAL_NET_PNL_BPS = 0.0
MIN_POSITIVE_FOLD_RATE = 1.0
MIN_POSITIVE_MONTH_RATE = 1.0
MIN_WIN_RATE = 0.50


def _write_report(payload: dict[str, object]) -> None:
    aggregate = payload["aggregate"]
    original = payload["original"]
    inverted = payload["inverted"]
    comparison = pd.DataFrame(
        [
            {"variant": "original", **original},
            {"variant": "inverted_signal", **inverted},
        ]
    )
    lines = [
        "# Research V82 BTCUSDC Signal Inversion Audit Results",
        "",
        "## Decision",
        "",
        f"- Promote inverted signal: `{aggregate['promote_inverted_signal']}`",
        f"- Failed checks: `{';'.join(aggregate['failed_checks'])}`",
        "",
        "## Gate",
        "",
        f"- Min total net PnL: `{MIN_TOTAL_NET_PNL_BPS}` bps",
        f"- Min positive fold rate: `{MIN_POSITIVE_FOLD_RATE}`",
        f"- Min positive month rate: `{MIN_POSITIVE_MONTH_RATE}`",
        f"- Min win rate: `{MIN_WIN_RATE}`",
        "",
        "## Original vs Inverted",
        "",
        comparison.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V82 tests whether the failed BTCUSDC public replay was simply a wrong-side signal. The inverted variant flips gross PnL and subtracts the same execution cost again, so it does not get free fees or free spread. Both original and inverted variants remain negative across every fold and every month.",
        "",
        "The result does not promote a strategy route. It closes the simple signal-inversion rescue idea: the issue is not just that long/short sides were swapped.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    if not INPUT_LEDGER.exists():
        raise SystemExit(f"missing input ledger: {INPUT_LEDGER}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    trades = pd.read_csv(INPUT_LEDGER)
    result = summarize_signal_inversion_viability(
        trades,
        min_total_net_pnl_bps=MIN_TOTAL_NET_PNL_BPS,
        min_positive_fold_rate=MIN_POSITIVE_FOLD_RATE,
        min_positive_month_rate=MIN_POSITIVE_MONTH_RATE,
        min_win_rate=MIN_WIN_RATE,
    )
    payload = {
        "version": "v82_btcusdc_signal_inversion_audit",
        "input_ledger": str(INPUT_LEDGER),
        **result,
        "outputs": {
            "summary_json": str(OUT_DIR / "v82_summary.json"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v82_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload)
    print(json.dumps(payload, indent=2, default=str))
