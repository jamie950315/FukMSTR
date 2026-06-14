# Research V11 Commands

All commands assume:

```bash
cd lob_microprice_lab
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .[dev]
```

## Verify code

```bash
python -m py_compile src/lob_microprice_lab/*.py
make test-split
```

## Run the main V11 sequential H90 source-rank audit

```bash
make sequential-h90-v11-source
```

Equivalent expanded command:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
PYTHONPATH=src python -m lob_microprice_lab.cli sequential-template-audit \
  --ensemble-dir runs/research_v09_ensemble_h90_5fold_stationary \
  --out runs/local_v11_seq_h90_5fold_source \
  --horizon-sec 90 \
  --cost-bps 1.5 \
  --latency-sec 0.5 \
  --edge-thresholds 0.1,0.2,0.3,0.5,0.7 \
  --signed-columns imbalance_l3,microprice_dev_bps_l3,mid_ret_60r_bps \
  --spread-quantiles 1.0 \
  --vol-modes none \
  --template-source first_fold \
  --min-source-trades 4 \
  --top-k-templates 80 \
  --period-sec 0 \
  --ranking-policy source_rank \
  --cold-start-policy source_rank \
  --warmup-periods 0 \
  --min-history-trades 0 \
  --min-history-periods 0 \
  --shift-null-runs 80 \
  --stress-cost-bps-values 1.5,3.0,5.0 \
  --stress-latency-sec-values 0,0.5,1.0,2.0 \
  --gate-min-oof-trades 20 \
  --gate-min-periods-with-trades 5 \
  --gate-min-period-mean-net-bps 0 \
  --clean
```

## Run the adaptive lower-bound selector

```bash
make sequential-h90-v11-lower
```

This selector uses past validation periods to choose the next template by lower confidence bound.  In V11 it fails and produces negative aggregate PnL.

## Run conservative micro-period stress

```bash
make sequential-h90-v11-microperiod
```

This splits each validation fold into 180-second segments and reruns the source-ranked H90 rule.  It is intentionally conservative because trades near period boundaries need enough future data to exit.  In V11 it turns negative.

## Run family-wise null on the H90 5-fold lead

```bash
make family-null-h90-v11-5fold
```

This checks whether the source-ranked lead remains exceptional after the full candidate family is subjected to shifted-signal null search.  In V11 it fails:

```text
p_family_null_max_total_ge_source_rank1: 0.4667
p_family_null_max_mean_ge_source_rank1: 0.75
```

## Important output files

```text
reports/RESEARCH_V11_RESULTS.md
runs/research_v11_summary.csv
runs/research_v11_seq_h90_5fold_source/REPORT.md
runs/research_v11_seq_h90_5fold_source/summary.json
runs/research_v11_family_null_h90_5fold/REPORT.md
runs/research_v11_family_null_h90_5fold/summary.json
```

## Read the online selection details

```bash
cat runs/research_v11_seq_h90_5fold_source/REPORT.md
python -m json.tool runs/research_v11_seq_h90_5fold_source/summary.json
```

## Suggested next experiment

Use this same command family on real multi-day ensembles after adding more Tardis/Binance Futures L2 + trades data.  The required validation pattern is:

```text
past sessions select the template
future session validates it
no validation-ranked template choice
family-wise null correction remains active
```
