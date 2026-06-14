# Research V04 Commands

Run tests:

```bash
make test-split
```

Stress existing OOF predictions:

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli stress \
  --predictions runs/research_v3_walk_forward_h10_base_2fold/oof_predictions.csv \
  --out runs/local_v04_stress_h10 \
  --horizon-sec 10 \
  --edge-thresholds 0.3,0.5,0.7,0.9 \
  --cost-bps-values 1.5,3.0 \
  --latency-sec-values 0,0.5,1.0 \
  --clean
```

Adaptive walk-forward, H5, zero latency:

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli adaptive-walk-forward \
  --book data/real_tardis/book_depth10_500ms.csv \
  --config configs/real_h10_base.yaml \
  --out runs/local_v04_adaptive_h5 \
  --horizon-sec 5 \
  --threshold-bps 1 \
  --model logistic \
  --candidate-edges 0.1,0.2,0.3,0.5,0.7,0.9 \
  --cost-bps 1.5 \
  --latency-sec 0 \
  --folds 2 \
  --min-train-ratio 0.5 \
  --valid-ratio 0.15 \
  --calibration-ratio 0.2 \
  --min-calibration-trades 20 \
  --clean
```

Adaptive walk-forward, H5, 0.5 second latency:

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli adaptive-walk-forward \
  --book data/real_tardis/book_depth10_500ms.csv \
  --config configs/real_h10_base.yaml \
  --out runs/local_v04_adaptive_h5_latency05 \
  --horizon-sec 5 \
  --threshold-bps 1 \
  --model logistic \
  --candidate-edges 0.1,0.2,0.3,0.5,0.7,0.9 \
  --cost-bps 1.5 \
  --latency-sec 0.5 \
  --folds 2 \
  --min-train-ratio 0.5 \
  --valid-ratio 0.15 \
  --calibration-ratio 0.2 \
  --min-calibration-trades 20 \
  --clean
```
