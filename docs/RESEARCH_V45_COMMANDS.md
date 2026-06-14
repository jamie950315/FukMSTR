# Research V45 Commands

V45 adds path-shape metrics to BTCUSDC candidate evaluations, reruns nested recency, then tests prequential meta-selection with the enhanced feature set.

```bash
make btcusdc-enhanced-meta-selector-v45
make test-btcusdc-v45
PYTHONPATH=src python -m py_compile src/lob_microprice_lab/*.py scripts/run_btcusdc_enhanced_meta_selector_v45.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
```

Inputs:

```text
runs/research_v36_btcusdc_aggtrade_flow_ytd_rolling_input/btcusdc_aggtrade_1m_flow_bars.csv
```

Outputs:

```text
runs/research_v45_btcusdc_enhanced_nested_recency/summary_v43.json
runs/research_v45_btcusdc_enhanced_nested_recency/btcusdc_v43_candidate_evaluations.csv
runs/research_v45_btcusdc_enhanced_meta_selector/summary_v45.json
runs/research_v45_btcusdc_enhanced_meta_selector/REPORT_V45.md
runs/research_v45_btcusdc_enhanced_meta_selector/btcusdc_v45_summary.csv
```
