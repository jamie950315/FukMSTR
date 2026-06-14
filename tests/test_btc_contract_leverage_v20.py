from pathlib import Path

import pandas as pd

from lob_microprice_lab.btc_contract_data import binance_um_daily_urls, write_btc_contract_data_plan
from lob_microprice_lab.btc_contract_leverage import _leverage_table, BTCContractLockGate


def test_binance_um_daily_url_builder():
    rows = binance_um_daily_urls(symbol="BTCUSDT", start="2020-04-01", end="2020-04-01", intervals=["1m"], data_types=["klines", "aggTrades"])
    assert len(rows) == 2
    assert rows[0]["url"].endswith("BTCUSDT-1m-2020-04-01.zip")
    assert rows[1]["url"].endswith("BTCUSDT-aggTrades-2020-04-01.zip")


def test_write_btc_contract_data_plan(tmp_path: Path):
    manifest = write_btc_contract_data_plan(tmp_path, start="2020-04-01", end="2020-04-02", intervals=["1m"])
    assert manifest["recommended_minimum_validation"]["independent_days"] == 20
    assert (tmp_path / "btc_contract_data_manifest.json").exists()
    assert (tmp_path / "BTC_CONTRACT_DATA_PLAN.md").exists()


def test_leverage_table_safety_flags():
    excursions = pd.DataFrame({"net_pnl_bps": [10.0, -2.0, 8.0], "mae_bps": [-5.0, -6.0, -4.0]})
    table = _leverage_table(excursions, leverage_grid=[1, 5, 10], gate=BTCContractLockGate(max_research_leverage=10))
    assert table["passes_research_safety"].all()
    assert table.loc[table["leverage"] == 10, "estimated_equity_total_return_pct"].iloc[0] > 0
