# Research V07 Commands

Run from the project root with `PYTHONPATH=src`.

## Verify code

```bash
python -m py_compile src/lob_microprice_lab/*.py
make test-split
```

## Reproduce the best V07 selective lead

This command uses the already-packaged leak-free H45 ensemble predictions from V06 and applies V07 calibration-only selective filters.

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli selective-from-ensemble \
  --ensemble-dir runs/research_v06_leakfree_stationary_logistic_h45_3fold_top80 \
  --out runs/local_v07_selective_h45_nospread \
  --horizon-sec 45 \
  --cost-bps 1.5 \
  --latency-sec 0.5 \
  --edge-thresholds 0.2,0.5,0.7 \
  --min-calibration-trades 8 \
  --stress-cost-bps-values 1.5,3.0,5.0 \
  --stress-latency-sec-values 0,0.5,1.0,2.0 \
  --signed-columns imbalance_l3,microprice_dev_bps_l3,mid_ret_60r_bps \
  --spread-quantiles 1.0 \
  --vol-modes none \
  --clean
```

Equivalent make target:

```bash
make selective-h45-v07
```

## Reproduce the 60/90/120s baseline sweep

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli long-horizon-sweep \
  --book data/real_tardis/book_depth10_500ms.csv \
  --config configs/real_h45_v06_long.yaml \
  --out runs/local_v07_long_sweep_stationary_logistic \
  --horizons-sec 60,90,120 \
  --thresholds-bps 1 \
  --model-sets 'logistic' \
  --top-k-features 80 \
  --candidate-edges 0.1,0.2,0.3,0.5,0.7 \
  --cost-bps 1.5 \
  --latency-sec 0.5 \
  --stress-cost-bps-values 1.5,3.0,5.0 \
  --stress-latency-sec-values 0,0.5,1.0,2.0 \
  --folds 3 \
  --min-train-ratio 0.45 \
  --valid-ratio 0.12 \
  --calibration-ratio 0.2 \
  --min-calibration-trades 8 \
  --stationary-only \
  --clean
```

## Reproduce the more stress-resistant sparse H45 variant

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli selective-from-ensemble \
  --ensemble-dir runs/research_v06_leakfree_stationary_logistic_h45_3fold_top80 \
  --out runs/local_v07_selective_h45_with_spread \
  --horizon-sec 45 \
  --cost-bps 1.5 \
  --latency-sec 0.5 \
  --edge-thresholds 0.2,0.5,0.7 \
  --min-calibration-trades 8 \
  --stress-cost-bps-values 1.5,3.0,5.0 \
  --stress-latency-sec-values 0,0.5,1.0,2.0 \
  --signed-columns imbalance_l3,microprice_dev_bps_l3,mid_ret_60r_bps \
  --spread-quantiles 1.0,0.75,0.5 \
  --vol-modes none,low,high,band \
  --clean
```

## Main V07 outputs

```text
reports/RESEARCH_V7_RESULTS.md
runs/research_v07_summary/leaderboard.csv
runs/research_v07_selective_h45_invertgrid_nospread/REPORT.md
runs/research_v07_selective_h45_invertgrid_nospread/oof_selective_backtest.csv
runs/research_v07_selective_h45_invertgrid_nospread/oof_fixed_signal_stress.csv
runs/research_v07_selective_h45_invertgrid_nospread/shift_null_fixed_signals.csv
```

## How to read V07 status

V07 has a single-day H45 research lead. It is positive at the primary 1.5 bps / 0.5s setting and beats shifted-signal nulls, but it fails strict promotion because the sample is small, bootstrap lower bounds are negative, and cost/latency stress is not strong enough.
