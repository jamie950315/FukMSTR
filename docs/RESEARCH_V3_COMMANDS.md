# Research v3 command cookbook

## Environment

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .[dev]
export PYTHONPATH=src
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
```

## Verification

```bash
python -m py_compile src/lob_microprice_lab/*.py
pytest -q
```

## Recreate the packaged Tardis sample

```bash
python -m lob_microprice_lab.cli fetch-tardis-sample \
  --out data/real_tardis \
  --depth 10 \
  --sample-ms 500 \
  --max-snapshots 10000 \
  --overwrite
```

## Profile and feature scan

```bash
python -m lob_microprice_lab.cli profile \
  --book data/real_tardis/book_depth10_500ms.csv \
  --config configs/research_fast.yaml \
  --out runs/local_profile

python -m lob_microprice_lab.cli feature-scan \
  --book data/real_tardis/book_depth10_500ms.csv \
  --config configs/research_fast.yaml \
  --out runs/local_feature_scan \
  --horizons-sec 1,5,10 \
  --threshold-bps 1 \
  --top-n 30
```

## H10 single split

```bash
python -m lob_microprice_lab.cli train \
  --book data/real_tardis/book_depth10_500ms.csv \
  --config configs/real_h10_base.yaml \
  --out runs/local_h10_base
```

## H10 walk-forward

```bash
python -m lob_microprice_lab.cli walk-forward \
  --book data/real_tardis/book_depth10_500ms.csv \
  --config configs/real_h10_base.yaml \
  --out runs/local_walk_forward_h10_base \
  --horizon-sec 10 \
  --threshold-bps 1 \
  --model logistic \
  --edge-threshold 0.5 \
  --edge-thresholds 0.1,0.2,0.3,0.5,0.7,0.9 \
  --folds 2 \
  --min-train-ratio 0.5 \
  --valid-ratio 0.15 \
  --no-null \
  --clean
```

## Rule baseline and feature ablation

```bash
python -m lob_microprice_lab.cli rule-baselines \
  --book data/real_tardis/book_depth10_500ms.csv \
  --config configs/real_h10_base.yaml \
  --out runs/local_rule_baselines_h10 \
  --clean

python -m lob_microprice_lab.cli ablate-features \
  --book data/real_tardis/book_depth10_500ms.csv \
  --config configs/real_h10_base.yaml \
  --out runs/local_ablation_h10 \
  --horizon-sec 10 \
  --threshold-bps 1 \
  --model logistic \
  --edge-threshold 0.5 \
  --clean
```

## Binance live public data capture

```bash
python -m lob_microprice_lab.cli collect-binance-ws \
  --out data/binance/BTCUSDT_ws_depth20.csv \
  --symbol BTCUSDT \
  --depth 20 \
  --sample-ms 1000 \
  --seconds 120
```
