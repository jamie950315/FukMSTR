from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btc_contract_data import BinancePublicFileSpec, download_file
from lob_microprice_lab.btcusdc_independent_validation import run_btcusdc_rolling_forward_validation


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
    interval = "1m"
    start = date(2026, 1, 1)
    end = date(2026, 6, 10)
    data_root = root / "data" / "binance_public"
    input_dir = root / "runs" / "research_v29_btcusdc_ytd_rolling_input"
    input_dir.mkdir(parents=True, exist_ok=True)

    downloaded: list[dict[str, object]] = []
    kline_paths: list[Path] = []
    for day in _date_range(start, end):
        spec = BinancePublicFileSpec(market="um", data_type="klines", symbol=symbol, interval=interval, date_value=day)
        path = download_file(spec.url(), spec.local_path(data_root), overwrite=False, timeout=60.0)
        downloaded.append({"date": day, "url": spec.url(), "path": str(path), "bytes": path.stat().st_size})
        kline_paths.append(path)
    pd.DataFrame(downloaded).to_csv(input_dir / "downloaded_btcusdc_1m_klines.csv", index=False)

    result = run_btcusdc_rolling_forward_validation(
        kline_paths=kline_paths,
        out_dir=root / "runs" / "research_v29_btcusdc_ytd_rolling",
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        calibration_days=20,
        validation_days=10,
        step_days=10,
        directions=("short",),
        filter_features=("volume_ratio",),
        min_calibration_trades=20,
        min_calibration_day_positive_rate=0.5,
        min_calibration_account_return_pct=25.0,
        leverage=8.0,
        fee_bps=8.5,
        target_account_return_pct=50.0,
        clean=True,
    )
    payload = {
        "downloaded_files": len(downloaded),
        "input_dir": str(input_dir),
        "out_dir": str(root / "runs" / "research_v29_btcusdc_ytd_rolling"),
        "aggregate": result["aggregate"],
    }
    (input_dir / "ytd_rolling_run_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
