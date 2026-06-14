from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btc_contract_data import BinancePublicFileSpec, download_file
from lob_microprice_lab.btcusdc_contract_lock import BTCUSDCContractPolicy, run_btcusdc_contract_lock
from lob_microprice_lab.btcusdc_public_replay import build_btcusdc_public_kline_replay_ledger


def _date_range(start: date, end: date) -> list[str]:
    out: list[str] = []
    cur = start
    while cur <= end:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    symbol = "BTCUSDC"
    interval = "1m"
    start = date(2026, 5, 22)
    end = date(2026, 6, 10)
    data_root = root / "data" / "binance_public"
    input_dir = root / "runs" / "research_v26_btcusdc_true_replay_input"
    out_dir = root / "runs" / "research_v26_btcusdc_true_replay"
    input_dir.mkdir(parents=True, exist_ok=True)

    downloaded: list[dict[str, object]] = []
    kline_paths: list[Path] = []
    for day in _date_range(start, end):
        spec = BinancePublicFileSpec(market="um", data_type="klines", symbol=symbol, interval=interval, date_value=day)
        target = spec.local_path(data_root)
        path = download_file(spec.url(), target, overwrite=False, timeout=60.0)
        downloaded.append({"date": day, "url": spec.url(), "path": str(path), "bytes": path.stat().st_size})
        kline_paths.append(path)

    pd.DataFrame(downloaded).to_csv(input_dir / "downloaded_btcusdc_1m_klines.csv", index=False)

    template_path = root / "runs" / "research_v24_btc_adaptive_exit_safety_lock" / "btc_adaptive_exit_trade_ledger.csv"
    template = pd.read_csv(template_path)
    ledger_path = input_dir / "btcusdc_public_1m_replay_ledger.csv"
    ledger = build_btcusdc_public_kline_replay_ledger(
        template_ledger=template,
        kline_paths=kline_paths,
        out_path=ledger_path,
        horizon_sec=90.0,
        latency_sec=0.5,
        taker_roundtrip_fee_bps=8.0,
    )

    result = run_btcusdc_contract_lock(
        v24_run_dir=root / "runs" / "research_v24_btc_adaptive_exit_safety_lock",
        out_dir=out_dir,
        policy=BTCUSDCContractPolicy(source_symbol="BTCUSDC Binance USD-M public 1m kline replay"),
        btcusdc_ledger=ledger_path,
        data_start=start.isoformat(),
        data_end=end.isoformat(),
        clean=True,
    )
    payload = {
        "downloaded_files": len(downloaded),
        "ledger_path": str(ledger_path),
        "ledger_rows": int(len(ledger)),
        "out_dir": str(out_dir),
        "aggregate": result["aggregate"],
    }
    (input_dir / "true_replay_run_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
