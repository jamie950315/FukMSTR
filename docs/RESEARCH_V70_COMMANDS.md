# Research V70 Fixed Flow Extended Validation Commands

## Purpose

V70 extends validation for the V69 BTCUSDC fixed-flow hour-gated strategy. It checks whether the positive result survives stricter views:

- prequential dynamic hour-gate re-selection,
- month and quarter summaries,
- exhaustive hour-exclusion combination comparison,
- simple post-loss risk-governor scans.

## Prerequisites

```bash
make btcusdc-fixed-flow-stability-v68
make btcusdc-fixed-flow-hour-gate-v69
```

## Run

```bash
make btcusdc-fixed-flow-extended-validation-v70
```

## Targeted Test

```bash
make test-btcusdc-v70
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

- `runs/research_v70_btcusdc_fixed_flow_extended_validation/v70_summary.json`
- `runs/research_v70_btcusdc_fixed_flow_extended_validation/v70_prequential_hour_gate.csv`
- `runs/research_v70_btcusdc_fixed_flow_extended_validation/v70_period_summary.csv`
- `runs/research_v70_btcusdc_fixed_flow_extended_validation/v70_risk_governor_scan.csv`
- `reports/RESEARCH_V70_FIXED_FLOW_EXTENDED_VALIDATION_RESULTS.md`

## Interpretation

V70 can retain V69 as the current best research candidate while refusing to upgrade it to a stronger claim if stricter checks fail.
