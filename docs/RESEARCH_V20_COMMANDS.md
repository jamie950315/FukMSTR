# Research V20 Commands

Run the promoted BTC contract leverage lock:

```bash
make btc-contract-leverage-v20
```

Generate the large BTCUSDT USD-M futures public-data manifest:

```bash
make btc-contract-data-plan-v20
```

Direct CLI for the data plan:

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli btc-contract-data-plan \
  --out runs/research_v20_btc_contract_data_plan \
  --symbol BTCUSDT \
  --start-date 2024-01-01 \
  --end-date 2026-06-10
```

Direct CLI for the BTC contract lock:

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli btc-contract-leverage-lock \
  --v17-run-dir runs/research_v17_execution_profit_lock_alpha0125_tp40 \
  --v19-run-dir runs/research_v19_real_fee_lock_taker0040_maker0000 \
  --out runs/local_v20_btc_contract_leverage_lock \
  --taker-fee-percent 0.0400 \
  --maker-fee-percent 0.0000 \
  --clean
```

Direct script for the promoted V20 run:

```bash
PYTHONPATH=src python scripts/run_btc_contract_leverage_lock_v20.py
```

Verify targeted tests:

```bash
python -m py_compile src/lob_microprice_lab/*.py scripts/*.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q \
  tests/test_real_fee_lock_v19.py \
  tests/test_btc_contract_data_v20.py \
  tests/test_btc_leverage_lock_v20.py
```

Download BTCUSDT public data outside the sandbox:

```bash
bash runs/research_v20_btc_contract_data_plan/download_commands.sh
```

Then use downloaded BTC contract data to build K-line caches and run forward validation without retuning V20 thresholds.
