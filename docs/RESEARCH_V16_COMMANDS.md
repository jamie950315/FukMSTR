# Research V16 Commands — Profit-Lock Certificate

V16 freezes the v15 promoted policy and audits it with sparse 1000-shift family nulls, extended stress, and winner-dependence checks.

## Main run

```bash
make profit-lock-v16
```

Equivalent direct script:

```bash
PYTHONPATH=src python scripts/run_profit_lock_v16.py
```

Equivalent CLI:

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli profit-lock-certificate \
  --base-ensemble-dir runs/research_v09_ensemble_h90_5fold_stationary \
  --kline-ensemble-dir runs/research_v13_kline_h90_5fold_stationary_v12folds \
  --out runs/research_v16_profit_lock_certificate_alpha0125 \
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

## Verification

```bash
PYTHONPATH=src python -m py_compile src/lob_microprice_lab/*.py scripts/run_profit_lock_v16.py
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests/test_profit_success_fast_v15.py tests/test_kline_guard_v15.py tests/test_profit_lock_v16.py
PYTHONPATH=src python -m lob_microprice_lab.cli profit-lock-certificate --help
make profit-lock-v16
```

## Outputs

```text
runs/research_v16_profit_lock_certificate_alpha0125/summary.json
runs/research_v16_profit_lock_certificate_alpha0125/REPORT.md
runs/research_v16_profit_lock_certificate_alpha0125/profit_lock_oof_backtest.csv
runs/research_v16_profit_lock_certificate_alpha0125/fold_metrics.csv
runs/research_v16_profit_lock_certificate_alpha0125/profit_lock_family_candidates.csv
runs/research_v16_profit_lock_certificate_alpha0125/profit_lock_sparse_family_shift_null.csv
runs/research_v16_profit_lock_certificate_alpha0125/profit_lock_extended_stress.csv
```
