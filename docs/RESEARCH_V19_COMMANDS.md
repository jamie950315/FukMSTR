# Research V19 Commands - Real-Fee Profit Lock

V19 continues from the frozen V17/V18 rule and uses the user-supplied fee schedule:

```text
taker fee = 0.0400% = 4 bps per side
maker fee = 0.0000% = 0 bps per side
taker entry + taker exit = 8 bps round trip
```

## Run the V19 certificate

```bash
make real-fee-lock-v19
```

Direct CLI equivalent:

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli real-fee-lock-certificate \
  --v17-run-dir runs/research_v17_execution_profit_lock_alpha0125_tp40 \
  --out runs/research_v19_real_fee_lock_taker0040_maker0000 \
  --taker-fee-percent 0.0400 \
  --maker-fee-percent 0.0000 \
  --horizon-sec 90 \
  --latency-sec 0.5 \
  --take-profit-bps 40 \
  --stop-loss-bps 0 \
  --shift-null-runs 1000 \
  --clean
```

## Read outputs

```bash
cat runs/research_v19_real_fee_lock_taker0040_maker0000/REPORT.md
cat runs/research_v19_real_fee_lock_taker0040_maker0000/summary.json
cat reports/RESEARCH_V19_RESULTS.md
```

Important output files:

```text
runs/research_v19_real_fee_lock_taker0040_maker0000/real_fee_lock_oof_backtest.csv
runs/research_v19_real_fee_lock_taker0040_maker0000/real_fee_lock_trade_ledger.csv
runs/research_v19_real_fee_lock_taker0040_maker0000/real_fee_v17_reprice.csv
runs/research_v19_real_fee_lock_taker0040_maker0000/real_fee_filter_family_candidates.csv
runs/research_v19_real_fee_lock_taker0040_maker0000/real_fee_filter_family_shift_null.csv
runs/research_v19_real_fee_lock_taker0040_maker0000/real_fee_latency_fee_stress.csv
runs/research_v19_real_fee_lock_taker0040_maker0000/real_fee_missed_trade_stress.csv
runs/research_v19_real_fee_lock_taker0040_maker0000/real_fee_extra_cost_reserve.csv
```

## Verify

```bash
python -m py_compile src/lob_microprice_lab/*.py scripts/*.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_real_fee_lock_v19.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_real_fee_lock_v19.py tests/test_deployment_lock_v18.py tests/test_profit_execution_lock_v17.py tests/test_exit_lock_v17.py
make real-fee-lock-v19
```

`make test-split` reached the first two blocks successfully in the sandbox and the final diagnostics/adaptive block passed when run separately.
