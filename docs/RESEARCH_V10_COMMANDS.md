# Research V10 Commands

V10 adds family-wise null correction for long-window template searches.

## H90 family-wise null audit

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli template-family-null-audit \
  --ensemble-dir runs/research_v07_long_sweep_stationary_logistic/h90p0_thr1p0_top80_logistic \
  --out runs/local_v10_family_null_h90 \
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
  --shift-runs 80 \
  --stress-cost-bps-values 1.5,3.0,5.0 \
  --stress-latency-sec-values 0,0.5,1.0,2.0 \
  --clean
```

Equivalent Makefile target:

```bash
make family-null-h90-v10
```

## H120 family-wise null audit

```bash
make family-null-h120-v10
```

## Fast smoke test

```bash
PYTHONPATH=src pytest -q tests/test_selection_bias_v10.py
```

## Full split test

```bash
make test-split
```

## Output interpretation

Read these files in each run directory:

```text
REPORT.md
summary.json
candidate_family_actual.csv
familywise_shift_null.csv
fold_rank_correlation.csv
```

Promotion requires:

```text
source-ranked template positive
oracle result beats family-wise shifted-signal null
family p(total) <= 0.05
family p(mean) <= 0.05
positive stress grid
positive fold bootstrap lower bound
100+ non-overlap trades
```

In the bundled single-day data, all V10 long-window audits fail this standard.
