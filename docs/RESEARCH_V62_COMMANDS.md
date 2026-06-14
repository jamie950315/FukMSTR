# Research V62 Commands

Purpose: stress-test the V60 design-selected sparse BTCUSDC rule on holdout folds only with delayed entries.

## Run

```bash
make btcusdc-sparse-tp-holdout-entry-delay-v62
```

## Targeted Tests

```bash
make test-btcusdc-v62
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Primary Outputs

```text
runs/research_v62_btcusdc_sparse_tp_holdout_entry_delay/v62_holdout_entry_delay_gate_summary.csv
runs/research_v62_btcusdc_sparse_tp_holdout_entry_delay/v62_summary.json
runs/research_v62_delay1_holdout_contract_gate/summary.json
runs/research_v62_delay60_holdout_contract_gate/summary.json
reports/RESEARCH_V62_HOLDOUT_ENTRY_DELAY_RESULTS.md
```
