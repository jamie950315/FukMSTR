# Research V43 Commands

V43 tests nested recency selection on the BTCUSDC aggTrade 1m flow bars. Each 20-day calibration window is split into a 10-day candidate-generator slice and a 10-day selector slice before the selected candidate is applied to the next 10-day validation window.

```bash
make btcusdc-nested-recency-v43
make test-btcusdc-v43
PYTHONPATH=src python -m py_compile src/lob_microprice_lab/*.py scripts/run_btcusdc_nested_recency_v43.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
```

Input:

```text
runs/research_v36_btcusdc_aggtrade_flow_ytd_rolling_input/btcusdc_aggtrade_1m_flow_bars.csv
```

Outputs:

```text
runs/research_v43_btcusdc_nested_recency/summary_v43.json
runs/research_v43_btcusdc_nested_recency/REPORT_V43.md
runs/research_v43_btcusdc_nested_recency/btcusdc_v43_fold_metrics.csv
runs/research_v43_btcusdc_nested_recency/btcusdc_v43_candidate_evaluations.csv
runs/research_v43_btcusdc_nested_recency/btcusdc_v43_validation_trades.csv
```
