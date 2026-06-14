# Research V18 commands

V18 starts from the frozen V17 execution-profit result. It does not change the entry rule, the K-line support guard, or the 40 bps take-profit rule. It audits whether the saved V17 ledger remains usable after practical live-trading failures.

## Plain use

```bash
cd lob_microprice_lab_research_v18_deployment_lock
make deployment-lock-v18
```

The command reads:

```text
runs/research_v17_execution_profit_lock_alpha0125_tp40/execution_lock_oof_backtest.csv
```

and writes:

```text
runs/research_v18_deployment_lock_certificate/
```

## CLI form

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli deployment-lock-certificate \
  --v17-run-dir runs/research_v17_execution_profit_lock_alpha0125_tp40 \
  --out runs/research_v18_deployment_lock_certificate \
  --horizon-sec 90 \
  --miss-probabilities 0.05,0.10,0.20,0.30,0.40,0.50 \
  --extra-cost-bps-values 0,1,2,3,5,7.5,10 \
  --combined-miss-probabilities 0.10,0.20,0.30,0.40,0.50 \
  --combined-extra-cost-bps-values 1,2,3,5 \
  --clock-block-counts 3,4,5,6,8,10,12 \
  --random-scenarios 10000 \
  --seed 18018 \
  --clean
```

## Files produced

```text
summary.json
REPORT.md
frozen_v17_trade_ledger.csv
clock_time_block_stability.csv
missed_trade_stress.csv
extra_cost_reserve.csv
combined_execution_failure_stress.csv
DONE.marker
```

## Test commands

```bash
python -m py_compile src/lob_microprice_lab/*.py scripts/*.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_deployment_lock_v18.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_deployment_lock_v18.py tests/test_profit_execution_lock_v17.py tests/test_exit_lock_v17.py
```

`make test-split` can still be used for a broader local check, but it may take longer than short sandbox limits.
