# Research V05 command cookbook

## Run tests

```bash
make test-split
```

## Reproduce the v05 H30 candidate

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli ensemble-walk-forward \
  --book data/real_tardis/book_depth10_500ms.csv \
  --config configs/real_h30_v05.yaml \
  --out runs/local_v05_ensemble_h30_taker \
  --horizon-sec 30 \
  --threshold-bps 1 \
  --models logistic,hgb \
  --candidate-edges 0.1,0.2,0.3,0.5,0.7 \
  --cost-bps 1.5 \
  --latency-sec 0.5 \
  --stress-cost-bps-values 1.5,3.0 \
  --stress-latency-sec-values 0,0.5,1.0 \
  --folds 2 \
  --min-train-ratio 0.5 \
  --valid-ratio 0.15 \
  --calibration-ratio 0.2 \
  --top-k-features 80 \
  --min-calibration-trades 10 \
  --clean
```

Equivalent Make target:

```bash
make ensemble-h30-v05
```

## Extended stress sweep

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli sweep-taker \
  --predictions runs/local_v05_ensemble_h30_taker/oof_taker_backtest.csv \
  --out runs/local_v05_ensemble_h30_taker/oof_taker_extreme_stress.csv \
  --horizon-sec 30 \
  --cost-bps-values 1.5,3.0,5.0 \
  --latency-sec-values 0,0.5,1.0,2.0 \
  --edge-thresholds 0.1,0.2,0.3,0.5,0.7
```

## Deterministic rule control

```bash
make rule-taker-h30-v05
```

## New CLI commands

```text
ensemble-walk-forward       calibration-selected probability ensemble with taker bid/ask execution
rule-taker-walk-forward     deterministic rule selection under the same execution model
backtest-taker              taker bid/ask non-overlap backtest for prediction CSVs
sweep-taker                 cost/latency/edge sweep for prediction CSVs
```

## Gate interpretation

A v05 `strict_research_pass` requires:

```text
all validation folds have positive mean net PnL
all fold bootstrap p05 mean PnL values are positive
all folds have at least 20 trades
robust profit gate passes on OOF stress sweep
```

Passing this gate means the local bundled sample contains a research candidate. It does not imply live tradability.
