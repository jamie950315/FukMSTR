# Research V17 Commands — Execution Profit-Lock Certificate

Run from the project root.

## Main V17 target

```bash
make execution-profit-lock-v17
```

Equivalent direct command:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src \
python scripts/run_profit_execution_lock_v17.py
```

## CLI form

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli execution-profit-lock-certificate \
  --base-ensemble-dir runs/research_v09_ensemble_h90_5fold_stationary \
  --kline-ensemble-dir runs/research_v13_kline_h90_5fold_stationary_v12folds \
  --out runs/research_v17_execution_profit_lock_alpha0125_tp40 \
  --horizon-sec 90 \
  --cost-bps 1.5 \
  --latency-sec 0.5 \
  --edge-threshold 0.1 \
  --kline-alpha 0.125 \
  --ofi-col ofi_sum_l5_norm \
  --ofi-quantile 0.9 \
  --kline-col kline_15s_rv_6_bps \
  --kline-quantile 0.0 \
  --kline-operator '>=' \
  --directional \
  --take-profit-bps 40.0 \
  --stop-loss-bps 0.0 \
  --exit-take-profit-bps-values 0,20,30,40,60,90 \
  --exit-stop-loss-bps-values 0 \
  --alpha-grid 0,0.025,0.05,0.075,0.1,0.125,0.15 \
  --ofi-cols ofi_sum_l3_norm,ofi_sum_l5_norm,ofi_sum_l10_norm \
  --ofi-quantiles 0.5,0.6,0.7,0.8,0.9 \
  --kline-cols kline_15s_rv_6_bps,kline_15s_rv_12_bps,kline_1m_rv_3_bps,kline_1m_range_z_6,kline_1s_rv_1_bps,kline_15m_ret_3_bps,kline_15s_signal \
  --kline-quantiles 0.0 \
  --stress-cost-bps-values 1.5,3.0,5.0,7.5,10.0 \
  --stress-latency-sec-values 0,0.5,1.0,2.0,3.0,5.0 \
  --shift-null-runs 1000 \
  --gate-max-addone-family-p 0.01 \
  --clean
```

## Validation commands

```bash
python -m py_compile src/lob_microprice_lab/*.py scripts/run_profit_execution_lock_v17.py
PYTHONPATH=src python -m lob_microprice_lab.cli execution-profit-lock-certificate --help
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_exit_lock_v17.py tests/test_profit_execution_lock_v17.py
make test-split
unzip -t lob_microprice_lab_research_v17_execution_profit_lock.zip
```

## Frozen V17 policy

```text
alpha = 0.125
edge threshold = 0.1
OFI veto = ofi_sum_l5_norm <= fold calibration q0.9
K-line guard = directional signal * kline_15s_rv_6_bps >= fold calibration q0.0
take-profit = 40 bps
stop-loss = disabled
reserve original 90s horizon = true
cost = 1.5 bps
latency = 0.5s
```

Do not tune this policy again on the bundled sample. The next valid step is independent multi-day forward validation.
