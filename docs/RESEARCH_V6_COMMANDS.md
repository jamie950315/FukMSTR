# Research V06 Commands

## Verify leakage fix and tests

```bash
PYTHONPATH=src python -m py_compile src/lob_microprice_lab/*.py
make test-split
PYTHONPATH=src pytest -q tests/test_long_horizon.py
```

## Run leak-free stationary H30

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli ensemble-walk-forward \
  --book data/real_tardis/book_depth10_500ms.csv \
  --config configs/real_h30_v05.yaml \
  --out runs/local_v06_leakfree_stationary_h30 \
  --horizon-sec 30 \
  --threshold-bps 1 \
  --models logistic \
  --candidate-edges 0.1,0.2,0.3,0.5,0.7 \
  --cost-bps 1.5 \
  --latency-sec 0.5 \
  --stress-cost-bps-values 1.5,3.0,5.0 \
  --stress-latency-sec-values 0,0.5,1.0,2.0 \
  --folds 3 \
  --min-train-ratio 0.45 \
  --valid-ratio 0.12 \
  --calibration-ratio 0.2 \
  --top-k-features 80 \
  --min-calibration-trades 8 \
  --stationary-only \
  --clean
```

## Run leak-free stationary H45

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli ensemble-walk-forward \
  --book data/real_tardis/book_depth10_500ms.csv \
  --config configs/real_h30_v05.yaml \
  --out runs/local_v06_leakfree_stationary_h45 \
  --horizon-sec 45 \
  --threshold-bps 1 \
  --models logistic \
  --candidate-edges 0.1,0.2,0.3,0.5,0.7 \
  --cost-bps 1.5 \
  --latency-sec 0.5 \
  --stress-cost-bps-values 1.5,3.0,5.0 \
  --stress-latency-sec-values 0,0.5,1.0,2.0 \
  --folds 3 \
  --min-train-ratio 0.45 \
  --valid-ratio 0.12 \
  --calibration-ratio 0.2 \
  --top-k-features 80 \
  --min-calibration-trades 8 \
  --stationary-only \
  --clean
```

## Run an automated 30s+ long-horizon sweep

This can be slow when `hgb` is included.

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli long-horizon-sweep \
  --book data/real_tardis/book_depth10_500ms.csv \
  --config configs/real_h45_v06_long.yaml \
  --out runs/local_v06_long_sweep \
  --horizons-sec 30,45,60,90 \
  --thresholds-bps 1 \
  --model-sets 'logistic;logistic,hgb' \
  --top-k-features 80,120 \
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

## Summarize completed long-window runs

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli summarize-long-runs \
  --runs runs/research_v06_leakfree_stationary_logistic_h30_3fold_top80 runs/research_v06_leakfree_stationary_logistic_h45_3fold_top80 \
  --out runs/local_v06_leakfree_summary/leaderboard.csv \
  --gate-min-fold-trades 10 \
  --gate-min-oof-trades 30 \
  --gate-min-oof-hit-rate 0.55
```

## Inspect selected features for leakage

```bash
grep -R "future_best" runs/research_v06_leakfree_stationary_logistic_h30_3fold_top80/*/selected_features.csv
```

Expected result: no matches.
