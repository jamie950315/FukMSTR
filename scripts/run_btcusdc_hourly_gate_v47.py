from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import audit_hourly_gate_transfer


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    source_dir = root / "runs" / "research_v45_btcusdc_enhanced_nested_recency"
    selector_path = source_dir / "btcusdc_v43_selector_trades.csv"
    validation_path = source_dir / "btcusdc_v43_validation_trades.csv"
    if not selector_path.exists() or not validation_path.exists():
        raise SystemExit(f"missing V45 nested trade files under {source_dir}")

    out_dir = root / "runs" / "research_v47_btcusdc_hourly_gate"
    out_dir.mkdir(parents=True, exist_ok=True)
    result = audit_hourly_gate_transfer(
        pd.read_csv(selector_path),
        pd.read_csv(validation_path),
        top_n_values=(1, 2, 3, 4, 6, 8, 12, 16, 24),
        leverage=8.0,
        target_account_return_pct=50.0,
    )
    pd.DataFrame(result["folds"]).to_csv(out_dir / "btcusdc_v47_hourly_gate_folds.csv", index=False)
    pd.DataFrame(result["summary"]).to_csv(out_dir / "btcusdc_v47_hourly_gate_summary.csv", index=False)
    payload = {
        "version": "v47_btcusdc_hourly_gate_transfer_audit",
        "selector_trades": str(selector_path),
        "validation_trades": str(validation_path),
        **result["aggregate"],
    }
    (out_dir / "summary_v47.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [
        "# V47 BTCUSDC Hourly Gate Transfer Audit",
        "",
        "V47 ranks hours by selector-window PnL for each selected candidate, then keeps validation trades only in the selected hours.",
        "",
        "## Aggregate",
        "",
        "```json",
        json.dumps(payload, indent=2),
        "```",
        "",
        "## Ranked Top-N Hour Gates",
        "",
        pd.DataFrame(result["summary"]).to_csv(index=False).strip(),
        "",
    ]
    (out_dir / "REPORT_V47.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "DONE_V47.marker").write_text("ok\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
