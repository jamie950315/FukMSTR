# Research V46 Commands

V46 tests fixed candidate-family transfer. It selects a family using folds 1-7 only, then evaluates the same family on held-out folds 8-14.

```bash
make btcusdc-fixed-family-transfer-v46
make test-btcusdc-v46
PYTHONPATH=src python -m py_compile src/lob_microprice_lab/*.py scripts/run_btcusdc_fixed_family_transfer_v46.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
```

Input:

```text
runs/research_v45_btcusdc_enhanced_nested_recency/btcusdc_v43_candidate_evaluations.csv
```

Outputs:

```text
runs/research_v46_btcusdc_fixed_family_transfer/summary_v46.json
runs/research_v46_btcusdc_fixed_family_transfer/REPORT_V46.md
runs/research_v46_btcusdc_fixed_family_transfer/btcusdc_v46_summary.csv
```
