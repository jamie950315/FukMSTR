# Research V61 Commands

Purpose: run holdout-only BTCUSDC sparse TP ledgers through the unchanged V26 contract gate.

## Run

```bash
make btcusdc-sparse-tp-holdout-contract-v61
```

## Targeted Tests

```bash
make test-btcusdc-v61
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Primary Outputs

```text
runs/research_v61_btcusdc_sparse_tp_holdout_contract/v61_summary.json
runs/research_v61_btcusdc_sparse_tp_holdout_contract/v61_v60_design_selected_reversal_1080_q099_holdout_source_ledger_for_contract_gate.csv
runs/research_v61_v60_design_selected_reversal_1080_q099_holdout_contract_gate/summary.json
runs/research_v61_fixed_v55_v57_reversal_1440_q0995_holdout_contract_gate/summary.json
reports/RESEARCH_V61_HOLDOUT_CONTRACT_GATE_RESULTS.md
```
