from __future__ import annotations

import io
import zipfile
from pathlib import Path

from lob_microprice_lab.btc_contract_data import (
    BinancePublicFileSpec,
    build_binance_btc_download_plan,
    parse_binance_public_zip,
    write_btc_contract_data_plan,
)


def test_binance_public_futures_url() -> None:
    spec = BinancePublicFileSpec(market="um", data_type="klines", symbol="BTCUSDT", interval="1m", date_value="2024-01-01")
    assert spec.filename() == "BTCUSDT-1m-2024-01-01.zip"
    assert spec.relative_path() == "um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01-01.zip"
    assert spec.url().endswith("/data/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01-01.zip")


def test_download_plan_rows() -> None:
    plan = build_binance_btc_download_plan(start_date="2024-01-01", end_date="2024-01-02", intervals=("1m", "5m"), include_agg_trades=True)
    assert len(plan) == 6
    assert set(plan["data_type"]) == {"klines", "aggTrades"}


def test_parse_kline_zip(tmp_path: Path) -> None:
    csv_text = "1704067200000,42000,42100,41900,42050,10,1704067259999,420500,50,6,252300,0\n"
    zpath = tmp_path / "BTCUSDT-1m-2024-01-01.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("BTCUSDT-1m-2024-01-01.csv", csv_text)
    df = parse_binance_public_zip(zpath, data_type="klines", interval="1m")
    assert list(df.columns)[:6] == ["timestamp", "open", "high", "low", "close", "volume"]
    assert float(df.loc[0, "close"]) == 42050.0
    assert int(df.loc[0, "trade_count"]) == 50


def test_parse_kline_zip_accepts_binance_header_aliases(tmp_path: Path) -> None:
    csv_text = (
        "open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore\n"
        "1704067200000,42000,42100,41900,42050,10,1704067259999,420500,50,6,252300,0\n"
    )
    zpath = tmp_path / "BTCUSDC-1m-2024-01-01.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("BTCUSDC-1m-2024-01-01.csv", csv_text)

    df = parse_binance_public_zip(zpath, data_type="klines", interval="1m")

    assert int(df.loc[0, "trade_count"]) == 50
    assert float(df.loc[0, "taker_buy_base_volume"]) == 6.0
    assert float(df.loc[0, "taker_buy_quote_volume"]) == 252300.0


def test_write_btc_contract_data_plan(tmp_path: Path) -> None:
    result = write_btc_contract_data_plan(out_dir=tmp_path, start_date="2024-01-01", end_date="2024-01-01", intervals=("1m",))
    assert result["rows"] == 2
    assert (tmp_path / "binance_btcusdt_public_download_plan.csv").exists()
    assert (tmp_path / "btc_contract_data_sources.json").exists()
