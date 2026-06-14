# Research V58 Commands

Purpose: audit the fixed V55/V57 sparse BTCUSDC TP80 next-open rule with negative controls.

## Run

```bash
make btcusdc-sparse-tp-null-audit-v58
```

## Targeted Tests

```bash
make test-btcusdc-v58
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Primary Outputs

```text
runs/research_v58_btcusdc_sparse_tp_null_audit/v58_observed_kline_entries.csv
runs/research_v58_btcusdc_sparse_tp_null_audit/v58_observed_kline_tp80_ledger.csv
runs/research_v58_btcusdc_sparse_tp_null_audit/v58_direction_flip_entries.csv
runs/research_v58_btcusdc_sparse_tp_null_audit/v58_direction_flip_tp80_ledger.csv
runs/research_v58_btcusdc_sparse_tp_null_audit/v58_direction_flip_source_ledger_for_contract_gate.csv
runs/research_v58_btcusdc_sparse_tp_null_audit/v58_random_time_null_summary.csv
runs/research_v58_btcusdc_sparse_tp_null_audit/v58_summary.json
runs/research_v58_btcusdc_direction_flip_contract_gate/summary.json
reports/RESEARCH_V58_NULL_AUDIT_RESULTS.md
```
