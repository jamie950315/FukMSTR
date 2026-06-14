# Research V15 Commands

Run the V15 fast triple-family profit success audit:

```bash
make profit-success-fast-v15
```

Equivalent raw command:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src \
python -m lob_microprice_lab.cli profit-success-fast \
  --base-ensemble-dir runs/research_v09_ensemble_h90_5fold_stationary \
  --kline-ensemble-dir runs/research_v13_kline_h90_5fold_stationary_v12folds \
  --out runs/local_v15_profit_success_fast_alpha0125 \
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
  --alpha-grid 0,0.025,0.05,0.075,0.1,0.125,0.15 \
  --ofi-cols ofi_sum_l3_norm,ofi_sum_l5_norm,ofi_sum_l10_norm \
  --ofi-quantiles 0.5,0.6,0.7,0.8,0.9 \
  --kline-cols kline_15s_rv_6_bps,kline_15s_rv_12_bps,kline_1m_rv_3_bps,kline_1m_range_z_6,kline_1s_rv_1_bps,kline_15m_ret_3_bps,kline_15s_signal \
  --kline-quantiles 0.0 \
  --stress-cost-bps-values 1.5,3.0,5.0 \
  --stress-latency-sec-values 0,0.5,1.0,2.0 \
  --shift-null-runs 40 \
  --gate-min-oof-trades 20 \
  --gate-min-folds-with-trades 5 \
  --gate-min-fold-mean-net-bps 0 \
  --gate-min-fold-total-net-bps 0 \
  --gate-min-bootstrap-mean-p05-bps 0 \
  --gate-max-family-p 0.05 \
  --clean
```

Important frozen policy for independent validation:

```text
alpha = 0.125
edge threshold = 0.1
OFI veto = ofi_sum_l5_norm <= calibration q0.9
K-line guard = directional signal * kline_15s_rv_6_bps >= calibration q0.0
horizon = 90s
cost = 1.5 bps
latency = 0.5s
```

Do not tune alpha, OFI quantile, K-line feature, or K-line quantile on the next independent validation sample.
