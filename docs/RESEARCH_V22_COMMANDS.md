# Research V22 Commands - BTC Rescue Profit Lock

V22 continues from the V20/V21 BTC contract research path.

## Main run

```bash
make btc-rescue-profit-lock-v22
```

Direct CLI:

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli btc-rescue-profit-lock \
  --v17-run-dir runs/research_v17_execution_profit_lock_alpha0125_tp40 \
  --out runs/research_v22_btc_rescue_profit_lock_tp52 \
  --taker-fee-percent 0.0400 \
  --maker-fee-percent 0.0000 \
  --take-profit-bps 52 \
  --stop-loss-bps 0 \
  --shift-null-runs 1000 \
  --random-scenarios 10000 \
  --clean
```

## Read outputs

```bash
cat runs/research_v22_btc_rescue_profit_lock_tp52/REPORT.md
cat runs/research_v22_btc_rescue_profit_lock_tp52/summary.json
cat runs/research_v22_btc_rescue_profit_lock_tp52/btc_rescue_profit_trade_ledger.csv
cat runs/research_v22_btc_rescue_profit_lock_tp52/btc_v20_v21_v22_comparison.csv
```

## Test

```bash
python -m py_compile src/lob_microprice_lab/*.py scripts/*.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btc_rescue_profit_lock_v22.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q \
  tests/test_btc_rescue_profit_lock_v22.py \
  tests/test_btc_profit_target_lock_v21.py \
  tests/test_btc_leverage_lock_v20.py
```

## Frozen V22 policy

```text
Fee assumption: taker 0.0400% per side, maker 0.0000% per side
Route used in research: taker entry + taker exit
Round-trip fee: 8 bps
Horizon: 90 sec
Latency: 0.5 sec
Stop loss: disabled
Take profit: 52 bps
Entry base: V19 high-fee filters + V20 BTC long-side guard
New rescue lane: long only, kline_15s_signal <= -0.70 and kline_1m_rv_3_bps >= 20.0
Leverage research cap: 3x
```

## Caveat

V22 is still based on the bundled BTC sample. Do not retune V22 on the same sample. The next step is independent multi-day BTCUSDT contract validation using the generated BTC contract data plan.
