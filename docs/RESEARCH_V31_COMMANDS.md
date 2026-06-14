# Research V31 Commands

V31 audits BTCUSDC selector policy stability on the existing YTD rolling broad-probe candidate evaluations.

```bash
make btcusdc-prequential-selector-v31
make test-btcusdc-v31
PYTHONPATH=src python -m py_compile src/lob_microprice_lab/*.py scripts/run_btcusdc_prequential_selector_v31.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
```

The selector audit does not redownload data and does not choose policies using the current validation fold. It reads:

```text
runs/research_v29_btcusdc_ytd_rolling_broad_probe/btcusdc_v28_candidate_evaluations.csv
```

The main outputs are:

```text
runs/research_v31_btcusdc_prequential_selector/summary_v31.json
runs/research_v31_btcusdc_prequential_selector/REPORT_V31.md
runs/research_v31_btcusdc_prequential_selector/btcusdc_v31_prequential_folds.csv
runs/research_v31_btcusdc_prequential_selector/btcusdc_v31_static_policy_summary.csv
```
