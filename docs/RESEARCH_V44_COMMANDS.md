# Research V44 Commands

V44 tests a prequential candidate-level meta-selector on the V43 nested recency candidate evaluations. Each run trains only on completed folds, then selects the highest predicted candidate in the next fold.

```bash
make btcusdc-prequential-meta-selector-v44
make test-btcusdc-v44
PYTHONPATH=src python -m py_compile src/lob_microprice_lab/*.py scripts/run_btcusdc_prequential_meta_selector_v44.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
```

Input:

```text
runs/research_v43_btcusdc_nested_recency/btcusdc_v43_candidate_evaluations.csv
```

Outputs:

```text
runs/research_v44_btcusdc_prequential_meta_selector/summary_v44.json
runs/research_v44_btcusdc_prequential_meta_selector/REPORT_V44.md
runs/research_v44_btcusdc_prequential_meta_selector/btcusdc_v44_summary.csv
runs/research_v44_btcusdc_prequential_meta_selector/btcusdc_v44_random_forest_warmup2_folds.csv
```
