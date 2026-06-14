# Research V42 Commands

V42 tests quantile-band selectors that avoid the very top calibration candidates.

```bash
make btcusdc-quantile-band-selector-v42
make test-btcusdc-v42
PYTHONPATH=src python -m py_compile src/lob_microprice_lab/*.py scripts/run_btcusdc_quantile_band_selector_v42.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
```

Inputs:

```text
runs/research_v36_btcusdc_aggtrade_flow_ytd_rolling/btcusdc_v28_candidate_evaluations.csv
runs/research_v29_btcusdc_ytd_rolling_broad_probe/btcusdc_v28_candidate_evaluations.csv
```

Outputs:

```text
runs/research_v42_btcusdc_quantile_band_selector/summary_v42.json
runs/research_v42_btcusdc_quantile_band_selector/REPORT_V42.md
```
