from __future__ import annotations

import json
from pathlib import Path

from lob_microprice_lab.btcusdc_independent_validation import run_btcusdc_nested_recency_validation


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    bars_path = root / "runs" / "research_v36_btcusdc_aggtrade_flow_ytd_rolling_input" / "btcusdc_aggtrade_1m_flow_bars.csv"
    if not bars_path.exists():
        raise SystemExit(f"missing BTCUSDC aggTrade flow bars: {bars_path}")

    result = run_btcusdc_nested_recency_validation(
        kline_paths=[bars_path],
        out_dir=root / "runs" / "research_v43_btcusdc_nested_recency",
        start_date="2026-01-01",
        end_date="2026-06-10",
        calibration_days=20,
        selector_days=10,
        validation_days=10,
        step_days=10,
        lookbacks=(5, 10, 15, 30, 60, 120, 240),
        horizons=(60, 120, 240),
        directions=("flow_momentum", "flow_reversal", "momentum", "reversal"),
        filter_features=("abs_flow_imbalance", "volume_ratio", "range_bps"),
        quantiles=(0.6, 0.7, 0.8, 0.85, 0.9, 0.94, 0.98),
        min_selector_trades=20,
        min_selector_day_positive_rate=0.5,
        leverage=8.0,
        fee_bps=8.5,
        target_account_return_pct=50.0,
        clean=True,
    )
    payload = {
        "bars_path": str(bars_path),
        "out_dir": str(root / "runs" / "research_v43_btcusdc_nested_recency"),
        "aggregate": result["aggregate"],
    }
    print(json.dumps(payload, indent=2))
