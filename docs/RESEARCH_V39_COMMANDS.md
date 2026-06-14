# Research V39 Commands

V39 tests whether BTCUSDC aggTrade-flow candidate families persist across completed folds strongly enough to select future folds without validation leakage.

```bash
make btcusdc-aggtrade-flow-ytd-family-selector-v39
make test-btcusdc-v39
PYTHONPATH=src python -m py_compile src/lob_microprice_lab/*.py scripts/run_btcusdc_aggtrade_flow_ytd_family_selector_v39.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
```

Input:

```text
runs/research_v36_btcusdc_aggtrade_flow_ytd_rolling/btcusdc_v28_candidate_evaluations.csv
```

Outputs:

```text
runs/research_v39_btcusdc_aggtrade_flow_ytd_family_selector/summary_v39.json
runs/research_v39_btcusdc_aggtrade_flow_ytd_family_selector/REPORT_V39.md
runs/research_v39_btcusdc_aggtrade_flow_ytd_family_selector/btcusdc_v39_family_selector_summary.csv
```
