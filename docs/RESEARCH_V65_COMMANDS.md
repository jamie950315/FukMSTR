# Research V65 Commands

V65 attributes the V64 dense delay scan failures to individual holdout signals.

It does not change the V60 design-selected rule, thresholds, or V26 gate settings. It reads V64 artifacts and produces signal-level fragility tables.

## Run audit

```bash
make btcusdc-sparse-tp-signal-fragility-v65
```

## Test

```bash
make test-btcusdc-v65
```

## Full verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Expected outputs

```text
runs/research_v65_btcusdc_sparse_tp_signal_fragility_audit/v65_signal_delay_fragility.csv
runs/research_v65_btcusdc_sparse_tp_signal_fragility_audit/v65_failed_delay_losing_trades.csv
runs/research_v65_btcusdc_sparse_tp_signal_fragility_audit/v65_summary.json
reports/RESEARCH_V65_SIGNAL_FRAGILITY_AUDIT_RESULTS.md
```
