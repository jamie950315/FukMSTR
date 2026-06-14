from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import (
    aggregate_btcusdc_aggtrades_to_bars,
    audit_candidate_selection_gap,
    audit_topk_portfolio_selector,
    load_btcusdc_aggtrades,
    run_btcusdc_independent_validation,
)


def _date_range(start: date, end: date) -> list[str]:
    days: list[str] = []
    cur = start
    while cur <= end:
        days.append(cur.isoformat())
        cur += timedelta(days=1)
    return days


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    start = date(2026, 5, 22)
    end = date(2026, 6, 10)
    input_dir = root / "runs" / "research_v41_btcusdc_aggtrade_5s_probe_input"
    input_dir.mkdir(parents=True, exist_ok=True)
    aggtrade_dir = root / "data" / "binance_public" / "binance" / "um" / "daily" / "aggTrades" / "BTCUSDC"

    frames: list[pd.DataFrame] = []
    used_files: list[dict[str, object]] = []
    for day in _date_range(start, end):
        path = aggtrade_dir / f"BTCUSDC-aggTrades-{day}.zip"
        if not path.exists():
            raise SystemExit(f"missing aggTrade file: {path}")
        trades = load_btcusdc_aggtrades([path])
        frames.append(aggregate_btcusdc_aggtrades_to_bars(trades, freq="5s"))
        used_files.append({"date": day, "path": str(path), "bytes": path.stat().st_size})
    pd.DataFrame(used_files).to_csv(input_dir / "used_btcusdc_aggtrades.csv", index=False)

    bars = pd.concat(frames, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
    bars_path = input_dir / "btcusdc_aggtrade_5s_flow_bars.csv"
    bars.to_csv(bars_path, index=False)

    validation = run_btcusdc_independent_validation(
        kline_paths=[bars_path],
        out_dir=root / "runs" / "research_v41_btcusdc_aggtrade_5s_probe",
        calibration_end="2026-05-31",
        validation_start="2026-06-01",
        lookbacks=(12, 36, 72, 144, 288),
        horizons=(12, 36, 72, 144, 288),
        directions=("flow_momentum", "flow_reversal", "momentum", "reversal"),
        filter_features=("abs_flow_imbalance", "volume_ratio", "range_bps"),
        quantiles=(0.6, 0.7, 0.8, 0.85, 0.9, 0.94, 0.98),
        min_calibration_trades=20,
        min_calibration_day_positive_rate=0.5,
        leverage=8.0,
        fee_bps=8.5,
        target_account_return_pct=50.0,
        clean=True,
    )
    out_dir = root / "runs" / "research_v41_btcusdc_aggtrade_5s_probe"
    evaluations = pd.read_csv(out_dir / "btcusdc_v27_candidate_evaluations.csv").assign(fold=1)
    oracle = audit_candidate_selection_gap(evaluations, target_account_return_pct=50.0)
    topk = audit_topk_portfolio_selector(
        evaluations,
        topk_values=(1, 2, 3, 5, 10, 20, 50),
        min_calibration_trades=20,
        min_calibration_day_positive_rate=0.0,
        target_account_return_pct=50.0,
    )
    (out_dir / "btcusdc_v41_oracle_gap.json").write_text(json.dumps(oracle, indent=2), encoding="utf-8")
    (out_dir / "btcusdc_v41_topk.json").write_text(json.dumps(topk["aggregate"], indent=2), encoding="utf-8")
    aggregate = {
        "version": "v41_btcusdc_aggtrade_5s_probe",
        "bars": int(len(bars)),
        "validation": validation["aggregate"],
        "oracle_gap": oracle["aggregate"],
        "topk": topk["aggregate"],
    }
    (out_dir / "summary_v41.json").write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
    lines = [
        "# V41 BTCUSDC AggTrade 5s Probe",
        "",
        "V41 tests whether shorter 5-second aggTrade bars improve the BTCUSDC selector problem on the V32 independent split.",
        "",
        "## Aggregate",
        "",
        "```json",
        json.dumps(aggregate, indent=2),
        "```",
        "",
    ]
    (out_dir / "REPORT_V41.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "DONE_V41.marker").write_text("ok\n", encoding="utf-8")
    print(json.dumps(aggregate, indent=2))
