# Research V14 Commands

V14 continues from the uploaded v12 baseline and the v13 K-line overlay.  It adds a stricter stability-lock audit for the fixed K-line alpha overlay.

## Main V14 stability-lock run

```bash
make kline-stability-lock-v14
```

Equivalent explicit command:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
PYTHONPATH=src python -m lob_microprice_lab.cli kline-stability-lock-audit \
  --base-ensemble-dir runs/research_v09_ensemble_h90_5fold_stationary \
  --kline-ensemble-dir runs/research_v13_kline_h90_5fold_stationary_v12folds \
  --out runs/local_v14_kline_stability_lock_alpha0125_h90 \
  --horizon-sec 90 \
  --cost-bps 1.5 \
  --latency-sec 0.5 \
  --selected-alpha 0.125 \
  --alpha-grid 0,0.025,0.05,0.075,0.1,0.125,0.15 \
  --edge-threshold 0.1 \
  --filter-col ofi_sum_l5_norm \
  --filter-operator '<=' \
  --filter-quantile 0.9 \
  --family-filter-cols ofi_sum_l3_norm,ofi_sum_l5_norm,ofi_sum_l10_norm \
  --family-quantiles 0.5,0.6,0.7,0.8,0.9 \
  --stress-cost-bps-values 1.5,3.0,5.0 \
  --stress-latency-sec-values 0,0.5,1.0,2.0 \
  --shift-null-runs 80 \
  --gate-max-family-p 0.05 \
  --write-selected-blend-dir runs/local_v14_kline_blend_alpha0125_h90_pruned \
  --clean
```

## What the command does

The selected V14 policy is intentionally fixed and small:

```text
blended_prob = 0.875 * v12_prob + 0.125 * kline_model_prob
edge threshold = 0.1
slot-preserving OFI veto = ofi_sum_l5_norm <= fold calibration q0.9
horizon = 90s
cost = 1.5 bps
latency = 0.5s
```

The audit then checks:

```text
selected shifted-signal null
alpha-family shifted-signal null
OFI-family shifted-signal null
union alpha/OFI shifted-signal null
cost/latency stress repricing
5 fold positivity
6 equal-trade chronological block positivity
leave-one-fold-out positivity
block bootstrap p05 > 0
```

## Regression tests

```bash
python -m py_compile src/lob_microprice_lab/*.py
make test-split
```

Or explicitly:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q \
  tests/test_features.py tests/test_labels.py tests/test_real_data.py tests/test_research_tools.py \
  tests/test_stress.py tests/test_execution_v05.py tests/test_long_horizon.py \
  tests/test_selective_v07.py tests/test_fixed_template_v08.py tests/test_trade_audit_v08.py \
  tests/test_portfolio_v08.py tests/test_v09_research_tools.py tests/test_selection_bias_v10.py \
  tests/test_sequential_selection_v11.py tests/test_slot_veto_v12.py \
  tests/test_kline_features_v13.py tests/test_kline_weighting_v13.py tests/test_profit_stability_v14.py
```
