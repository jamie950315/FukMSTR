from __future__ import annotations

from pathlib import Path

import pandas as pd

from lob_microprice_lab.btc_contract_data import BtcContractDataSpec, build_public_data_manifest
from lob_microprice_lab.btcusdc_public_replay import build_btcusdc_public_kline_replay_ledger
from lob_microprice_lab.btcusdc_contract_lock import BTCUSDCContractPolicy, _prepare_btcusdc_ledger, run_btcusdc_contract_lock


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_btcusdc_manifest_urls_use_symbol() -> None:
    rows = build_public_data_manifest(
        BtcContractDataSpec(symbol="BTCUSDC", start_date="2026-06-10", end_date="2026-06-10", intervals=("1s", "1m"), include_klines=True, include_agg_trades=True, include_trades=True)
    )
    urls = [r.url for r in rows]
    assert len(rows) == 4
    assert all("BTCUSDC" in u for u in urls)
    assert any("/futures/um/daily/klines/BTCUSDC/1s/" in u for u in urls)
    assert any("/futures/um/daily/aggTrades/BTCUSDC/" in u for u in urls)
    assert any("/futures/um/daily/trades/BTCUSDC/" in u for u in urls)


def test_prepare_btcusdc_ledger_subtracts_quote_surcharge() -> None:
    src = pd.DataFrame({"timestamp": ["2026-01-01T00:00:00Z"], "net_pnl_bps": [10.0], "cost_bps": [8.0], "fold": [1], "signal": [1]})
    out = _prepare_btcusdc_ledger(src, BTCUSDCContractPolicy(quote_transfer_surcharge_bps=0.5))
    assert out.loc[0, "symbol"] == "BTCUSDC"
    assert out.loc[0, "data_mode"] == "transfer_proxy_from_frozen_btc_ledger"
    assert out.loc[0, "net_pnl_bps"] == 9.5
    assert out.loc[0, "cost_bps"] == 8.5


def test_run_btcusdc_contract_lock_gate_passes(tmp_path: Path) -> None:
    root = _root()
    result = run_btcusdc_contract_lock(
        v24_run_dir=root / "runs" / "research_v24_btc_adaptive_exit_safety_lock",
        out_dir=tmp_path / "btcusdc",
        data_start="2026-06-10",
        data_end="2026-06-10",
        clean=True,
    )
    agg = result["aggregate"]
    assert agg["symbol"] == "BTCUSDC"
    assert agg["gate"]["passed"] is True
    assert agg["true_btcusdc_data_run_completed"] is False
    assert agg["btcusdc_transfer_proxy_completed"] is True
    assert agg["data_plan_rows"] == 8
    assert (tmp_path / "btcusdc" / "btcusdc_contract_trade_ledger.csv").exists()


def test_build_btcusdc_public_kline_replay_ledger_uses_real_kline_path(tmp_path: Path) -> None:
    template = pd.DataFrame(
        {
            "timestamp": ["2020-04-01T00:00:00Z"],
            "signal": [1],
            "fold": [1],
            "take_profit_bps": [20.0],
        }
    )
    klines = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-06-01T00:00:00Z", "2026-06-01T00:01:00Z", "2026-06-01T00:02:00Z"], utc=True),
            "open": [100.0, 100.0, 100.0],
            "high": [100.1, 100.4, 100.2],
            "low": [99.9, 99.8, 99.7],
            "close": [100.0, 100.3, 100.1],
            "volume": [1.0, 2.0, 3.0],
        }
    )
    kline_path = tmp_path / "klines.csv"
    klines.to_csv(kline_path, index=False)

    ledger = build_btcusdc_public_kline_replay_ledger(
        template_ledger=template,
        kline_paths=[kline_path],
        out_path=tmp_path / "ledger.csv",
        horizon_sec=90.0,
        latency_sec=0.0,
        taker_roundtrip_fee_bps=8.0,
    )

    assert len(ledger) == 1
    assert ledger.loc[0, "symbol"] == "BTCUSDC"
    assert ledger.loc[0, "data_mode"] == "true_btcusdc_public_kline_replay"
    assert ledger.loc[0, "exit_reason"] == "take_profit"
    assert abs(float(ledger.loc[0, "gross_pnl_bps"]) - 20.0) < 1e-9
    assert abs(float(ledger.loc[0, "net_pnl_bps"]) - 12.0) < 1e-9
    assert ledger.loc[0, "template_timestamp"] == "2020-04-01T00:00:00Z"
    assert (tmp_path / "ledger.csv").exists()
