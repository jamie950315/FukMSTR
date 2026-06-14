# Research V69 Fixed Flow Hour Gate Commands

## Purpose

V69 applies a design-only hour exclusion gate to the V68 fixed BTCUSDC aggTrade-flow policy. The excluded hours are selected from design folds 1-4 only. Holdout folds 5-7 are used only for evaluation.

## Prerequisite

```bash
make btcusdc-fixed-flow-stability-v68
```

## Run

```bash
make btcusdc-fixed-flow-hour-gate-v69
```

## Targeted Test

```bash
make test-btcusdc-v69
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

- `runs/research_v69_btcusdc_fixed_flow_hour_gate/v69_summary.json`
- `runs/research_v69_btcusdc_fixed_flow_hour_gate/v69_hour_gated_trade_ledger.csv`
- `runs/research_v69_btcusdc_fixed_flow_hour_gate/v69_fold_summary.csv`
- `runs/research_v69_btcusdc_fixed_flow_hour_gate/v69_delay_summary.csv`
- `runs/research_v69_btcusdc_fixed_flow_hour_gate/v69_extra_cost_summary.csv`
- `reports/RESEARCH_V69_FIXED_FLOW_HOUR_GATE_RESULTS.md`

## Pass Standard

V69 must pass the V68 fixed-policy stability checks, the design-only hour gate must pass on folds 1-4, and all holdout folds 5-7 must be positive after fees.
