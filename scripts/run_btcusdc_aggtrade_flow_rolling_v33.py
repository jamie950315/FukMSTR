from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btc_contract_data import BinancePublicFileSpec, download_file
from lob_microprice_lab.btcusdc_independent_validation import (
    aggregate_btcusdc_aggtrades_to_bars,
    load_btcusdc_aggtrades,
    run_btcusdc_rolling_forward_validation,
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
    symbol = "BTCUSDC"
    start = date(2026, 3, 13)
    end = date(2026, 6, 10)
    data_root = root / "data" / "binance_public"
    input_dir = root / "runs" / "research_v33_btcusdc_aggtrade_flow_rolling_input"
    input_dir.mkdir(parents=True, exist_ok=True)

    downloaded: list[dict[str, object]] = []
    bar_frames: list[pd.DataFrame] = []
    for day in _date_range(start, end):
        spec = BinancePublicFileSpec(market="um", data_type="aggTrades", symbol=symbol, interval=None, date_value=day)
        path = download_file(spec.url(), spec.local_path(data_root), overwrite=False, timeout=120.0)
        downloaded.append({"date": day, "url": spec.url(), "path": str(path), "bytes": path.stat().st_size})
        trades = load_btcusdc_aggtrades([path])
        bar_frames.append(aggregate_btcusdc_aggtrades_to_bars(trades, freq="1min"))
    pd.DataFrame(downloaded).to_csv(input_dir / "downloaded_btcusdc_aggtrades.csv", index=False)

    bars = pd.concat(bar_frames, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
    bars_path = input_dir / "btcusdc_aggtrade_1m_flow_bars.csv"
    bars.to_csv(bars_path, index=False)

    result = run_btcusdc_rolling_forward_validation(
        kline_paths=[bars_path],
        out_dir=root / "runs" / "research_v33_btcusdc_aggtrade_flow_rolling",
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        calibration_days=20,
        validation_days=10,
        step_days=10,
        lookbacks=(5, 10, 15, 30, 60, 120, 240),
        horizons=(60, 120, 240),
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
    payload = {
        "downloaded_files": len(downloaded),
        "bars": int(len(bars)),
        "input_dir": str(input_dir),
        "bars_path": str(bars_path),
        "out_dir": str(root / "runs" / "research_v33_btcusdc_aggtrade_flow_rolling"),
        "aggregate": result["aggregate"],
    }
    (input_dir / "aggtrade_flow_rolling_run_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
