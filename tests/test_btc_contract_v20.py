from pathlib import Path

import pandas as pd

from lob_microprice_lab.btc_contract_data import binance_vision_url, build_binance_btcusdt_um_manifest
from lob_microprice_lab.btc_leverage_lock import BTCLeverageGate, run_btc_contract_leverage_lock
from lob_microprice_lab.real_fee_lock import RealFeeSpec


def test_binance_vision_btcusdt_url_shapes():
    daily = binance_vision_url(symbol="BTCUSDT", period="daily", data_type="klines", interval="1m", day="2025-01-02")
    assert daily.endswith("/data/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2025-01-02.zip")
    monthly = binance_vision_url(symbol="BTCUSDT", period="monthly", data_type="aggTrades", interval="", day="2025-01-02")
    assert monthly.endswith("/data/futures/um/monthly/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2025-01.zip")


def test_manifest_counts():
    rows = build_binance_btcusdt_um_manifest(start_date="2025-01-01", end_date="2025-01-02", intervals=("1m", "5m"), include_agg_trades=True)
    assert len(rows) == 6
    assert all(r.symbol == "BTCUSDT" for r in rows)


def test_btc_contract_leverage_lock_runs(tmp_path: Path):
    out = tmp_path / "v20"
    result = run_btc_contract_leverage_lock(
        v17_run_dir=Path("runs/research_v17_execution_profit_lock_alpha0125_tp40"),
        out_dir=out,
        fee_spec=RealFeeSpec(taker_fee_percent=0.0400, maker_fee_percent=0.0000),
        shift_null_runs=20,
        random_scenarios=200,
        write_data_plan=False,
        gate=BTCLeverageGate(max_side_guard_addone_p=0.10),
        clean=True,
    )
    agg = result["aggregate"]
    assert agg["trades"] == 10
    assert agg["hit_rate"] == 1.0
    assert agg["total_net_pnl_bps"] > 120
    assert agg["gate"]["passed"] is True
    ledger = pd.read_csv(out / "btc_contract_trade_ledger.csv")
    assert len(ledger) == 10
