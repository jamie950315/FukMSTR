# Research V26 Results: BTCUSDC Contract Lock

V26 responds to the BTCUSDC request. It keeps the V24/V25 BTC trade rule frozen and runs it in BTCUSDC contract mode. Because the build sandbox cannot download external Binance public-data files, this package has two modes:

1. **BTCUSDC transfer proxy mode**: run immediately from the frozen BTC trade ledger, subtracting a BTCUSDC quote-market surcharge and generating all BTCUSDC data manifests.
2. **True BTCUSDC ledger mode**: pass a real BTCUSDC trade ledger with the same schema to `run_btcusdc_contract_lock(..., btcusdc_ledger=...)`.

Only mode 2 can be counted as independent BTCUSDC proof. The included run is mode 1.

## Command

```bash
make btcusdc-contract-lock-v26
```

Main run:

```text
runs/research_v26_btcusdc_contract_lock
```

## Policy

```text
symbol: BTCUSDC
source: frozen V24/V25 BTC trade ledger transfer proxy
fee: 4 bps taker per side, 0 bps maker per side
route: taker entry + taker exit
round trip fee: 8 bps
BTCUSDC quote-market surcharge: 0.5 bps per trade
prediction window: 90 seconds
normal leverage: 8x
emergency leverage: 6.5x
emergency duration: 12 trades after a realized trade <= -20 bps
```

## Main result

| Metric | V26 BTCUSDC transfer proxy |
|---|---:|
| Gate passed | true |
| Data mode | transfer proxy from frozen BTC ledger |
| True BTCUSDC data run completed | false |
| Trades | 11 |
| Selected-trade win rate | 100.00% |
| Notional total net PnL | +184.5977 bps |
| Notional mean net PnL | +16.7816 bps/trade |
| Notional median net PnL | +13.7522 bps/trade |
| Worst trade | +0.2219 bps |
| Notional max drawdown | 0.0000 bps |
| Account return at 8x, no compounding | +14.7678% |
| Account max drawdown | 0.0000% |
| Bootstrap total p05 | +96.1782 bps |
| Bootstrap mean p05 | +8.7435 bps/trade |

## Stability checks

| Check | Result |
|---|---:|
| Worst fold total | +5.9553 bps |
| Worst fold mean | +2.9776 bps/trade |
| 5-block worst total | +18.1454 bps |
| 10-block worst total | +0.2426 bps |
| 10 bps/side + 5 sec account return | +3.1324% |
| 50% missed-trade p05 account return | +1.9031% |
| Extra +16 bps/trade account return | +0.6878% |
| Four synthetic -40 bps failures min account return | +0.9989% |
| Four synthetic -40 bps failures worst drawdown | -9.8206% |
| Approx liquidation buffer before safety shock | 1191.5 bps |

## BTCUSDC data plan

V26 generated a BTCUSDC Binance public-data plan:

```text
runs/research_v26_btcusdc_contract_lock/btcusdc_data_plan
rows: 7136
symbol: BTCUSDC
range: 2024-01-01 through 2026-06-10
intervals: 1s, 5s, 15s, 1m, 5m, 15m
includes: klines, aggTrades, trades
```

Run the generated downloader on a machine with internet access:

```bash
bash runs/research_v26_btcusdc_contract_lock/btcusdc_data_plan/download_commands.sh
```

Then convert or replay those files into a BTCUSDC ledger and call:

```python
from lob_microprice_lab.btcusdc_contract_lock import run_btcusdc_contract_lock

run_btcusdc_contract_lock(
    v24_run_dir="runs/research_v24_btc_adaptive_exit_safety_lock",
    out_dir="runs/research_v26_btcusdc_true_replay",
    btcusdc_ledger="path/to/real_btcusdc_trade_ledger.csv",
    clean=True,
)
```

## Caveat

The V26 gate passed for the BTCUSDC transfer proxy. It did **not** complete a true independent BTCUSDC order-book replay because no real BTCUSDC ledger is bundled and the sandbox could not download external public files. Live stable profit is still not proven until true BTCUSDC data is replayed without retuning.
