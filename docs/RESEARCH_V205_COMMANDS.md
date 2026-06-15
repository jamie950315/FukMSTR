# V205 Execution Validation Commands

V205 validates external execution evidence for the V204 real-money readiness gate.
It does not place live orders, tune thresholds, change entries, change exits, or change leverage rules.

## Default Run

```bash
make btcusdc-v205-execution-validation
```

The default run looks for:

- `runs/research_v205_execution_validation/fill_audit.csv`
- `runs/research_v205_execution_validation/kill_switch_events.csv`

It writes the V204-compatible execution summary to:

- `runs/research_v204_real_money_execution_validation/execution_validation_summary.json`

## Custom Evidence Files

```bash
PYTHONPATH=src python scripts/run_btcusdc_v205_execution_validation.py \
  --fills runs/research_v205_execution_validation/fill_audit.csv \
  --kill-switch-events runs/research_v205_execution_validation/kill_switch_events.csv
```

## Required Fill Audit Columns

`fill_audit.csv` must contain:

- `timestamp`
- `symbol`
- `side`
- `intended_price`
- `fill_price`
- `status`

The gate requires at least 30 fills, every fill status must be `filled`, and p95 absolute slippage must be at most 5 bps.

## Required Kill-Switch Evidence

`kill_switch_events.csv` must contain an `event_type` column with at least one row equal to:

```text
kill_switch_tested
```

## Focused Test

```bash
make test-btcusdc-v205
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

- `reports/RESEARCH_V205_BTCUSDC_EXECUTION_VALIDATION.md`
- `runs/research_v204_real_money_execution_validation/execution_validation_summary.json`

The `runs/` output is local generated evidence and should not be committed.
