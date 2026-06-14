from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from lob_microprice_lab.btcusdc_independent_validation import run_btcusdc_independent_validation


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    kline_dir = root / "data" / "binance_public" / "binance" / "um" / "daily" / "klines" / "BTCUSDC" / "1m"
    start = date(2026, 5, 22)
    end = date(2026, 6, 10)
    kline_paths = [
        path
        for path in sorted(kline_dir.glob("BTCUSDC-1m-2026-*.zip"))
        if start <= date.fromisoformat(path.stem.rsplit("-", 3)[-3] + "-" + path.stem.rsplit("-", 3)[-2] + "-" + path.stem.rsplit("-", 3)[-1]) <= end
    ]
    if len(kline_paths) < 20:
        raise SystemExit(f"expected at least 20 BTCUSDC 1m kline files, found {len(kline_paths)} in {kline_dir}")

    result = run_btcusdc_independent_validation(
        kline_paths=kline_paths,
        out_dir=root / "runs" / "research_v27_btcusdc_independent_validation",
        calibration_end="2026-05-31",
        validation_start="2026-06-01",
        directions=("short",),
        filter_features=("volume_ratio",),
        min_calibration_trades=20,
        min_calibration_day_positive_rate=0.5,
        leverage=8.0,
        fee_bps=8.5,
        target_account_return_pct=50.0,
        clean=True,
    )
    print(json.dumps(result, indent=2))
