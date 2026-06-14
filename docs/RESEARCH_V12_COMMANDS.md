# Research V12 Commands

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

## Run the main V12 gate-passing slot-veto audit

```bash
make slot-veto-h90-v12
```

Equivalent expanded command:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
PYTHONPATH=src python -m lob_microprice_lab.cli slot-veto-audit \
  --ensemble-dir runs/research_v09_ensemble_h90_5fold_stationary \
  --out runs/local_v12_slot_veto_h90_ofi_l5_q90 \
  --horizon-sec 90 \
  --cost-bps 1.5 \
  --latency-sec 0.5 \
  --edge-threshold 0.1 \
  --filter-col ofi_sum_l5_norm \
  --filter-operator '<=' \
  --filter-quantile 0.9 \
  --family-filter-cols ofi_sum_l3_norm,ofi_sum_l5_norm,ofi_sum_l10_norm \
  --family-quantiles 0.5,0.6,0.7,0.8,0.9 \
  --stress-cost-bps-values 1.5,3.0,5.0 \
  --stress-latency-sec-values 0,0.5,1.0,2.0 \
  --shift-null-runs 80 \
  --family-shift-runs 80 \
  --gate-min-oof-trades 20 \
  --gate-min-periods-with-trades 5 \
  --gate-min-period-mean-net-bps 0 \
  --gate-max-family-null-p-total 0.05 \
  --gate-max-family-null-p-mean 0.10 \
  --clean
```

## Important output files

```text
reports/RESEARCH_V12_RESULTS.md
runs/research_v12_summary.csv
runs/research_v12_slot_veto_h90_ofi_l5_q90/REPORT.md
runs/research_v12_slot_veto_h90_ofi_l5_q90/summary.json
runs/research_v12_slot_veto_h90_ofi_l5_q90/fold_metrics.csv
runs/research_v12_slot_veto_h90_ofi_l5_q90/slot_veto_stress.csv
runs/research_v12_slot_veto_h90_ofi_l5_q90/slot_veto_family_candidates.csv
runs/research_v12_slot_veto_h90_ofi_l5_q90/slot_veto_family_shift_null.csv
```

## Interpretation

The slot-veto audit is intentionally conservative.  It first creates the model's non-overlapping H90 slots, then vetoes scheduled entries using only calibration-derived OFI thresholds.  Vetoed slots reserve their original cooldown interval, so the strategy does not get replacement opportunities after rejecting a slot.

The main V12 run passes the single-day research gate.  Stable-profit evidence still requires multi-day L2 data and session-level validation.
