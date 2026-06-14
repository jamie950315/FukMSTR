# Research V09 Commands

V09 adds three long-window research workflows.

## 1. Prequential template-transfer audit

This is the most important V09 command.  It ranks fixed templates using past validation folds only, then tests on the next validation fold.

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli template-transfer-audit \
  --ensemble-dir runs/research_v07_long_sweep_stationary_logistic/h90p0_thr1p0_top80_logistic \
  --out runs/local_v09_template_transfer_h90 \
  --horizon-sec 90 \
  --cost-bps 1.5 \
  --latency-sec 0.5 \
  --edge-thresholds 0.1,0.2,0.3,0.5,0.7 \
  --signed-columns imbalance_l3,microprice_dev_bps_l3,mid_ret_60r_bps \
  --spread-quantiles 1.0 \
  --vol-modes none \
  --min-source-trades 4 \
  --top-k-templates 80 \
  --warmup-folds 1 \
  --min-history-trades 3 \
  --stress-cost-bps-values 1.5,3.0,5.0 \
  --stress-latency-sec-values 0,0.5,1.0,2.0 \
  --clean
```

Shortcut:

```bash
make template-transfer-h90-v09
```

## 2. Family-adaptive audit

This freezes a qualitative family, then lets each fold tune numeric thresholds from calibration only.

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli family-adaptive-audit \
  --ensemble-dir runs/research_v07_long_sweep_stationary_logistic/h90p0_thr1p0_top80_logistic \
  --family-json runs/research_v08_fixed_template_h90_validation_rank/selected_candidate.json \
  --out runs/local_v09_family_h90 \
  --horizon-sec 90 \
  --cost-bps 1.5 \
  --latency-sec 0.5 \
  --edge-thresholds 0.1,0.2,0.3,0.5,0.7 \
  --signed-abs-quantiles 0,0.25,0.5,0.75,0.9 \
  --spread-quantiles 1.0 \
  --vol-modes none \
  --min-calibration-trades 4 \
  --stress-cost-bps-values 1.5,3.0,5.0 \
  --stress-latency-sec-values 0,0.5,1.0,2.0 \
  --clean
```

Shortcut:

```bash
make family-h90-v09
```

## 3. Calibrated-edge audit

This learns a fold-local probability-edge mapping from calibration rows only, then reruns selective trading.

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli calibrated-edge-audit \
  --ensemble-dir runs/research_v07_long_sweep_stationary_logistic/h90p0_thr1p0_top80_logistic \
  --out runs/local_v09_calibrated_edge_h90 \
  --horizon-sec 90 \
  --cost-bps 1.5 \
  --latency-sec 0.5 \
  --calibrator logistic \
  --edge-thresholds 0.05,0.1,0.2,0.3,0.5,0.7 \
  --signed-columns imbalance_l3,microprice_dev_bps_l3,mid_ret_60r_bps \
  --spread-quantiles 1.0 \
  --vol-modes none \
  --min-calibration-trades 4 \
  --min-train-labels 50 \
  --stress-cost-bps-values 1.5,3.0,5.0 \
  --stress-latency-sec-values 0,0.5,1.0,2.0 \
  --clean
```

Shortcut:

```bash
make calibrated-edge-h90-v09
```

## Verification

```bash
python -m py_compile src/lob_microprice_lab/*.py
make test-split
```

Expected test coverage includes `tests/test_v09_research_tools.py`.
