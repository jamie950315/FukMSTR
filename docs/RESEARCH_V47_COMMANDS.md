# Research V47 Commands

V47 tests hour-of-day transfer for the selected BTCUSDC nested-recency candidates. It ranks hours by selector-window PnL only, then keeps validation trades from the selected hours.

```bash
make btcusdc-hourly-gate-v47
make test-btcusdc-v47
PYTHONPATH=src python -m py_compile src/lob_microprice_lab/*.py scripts/run_btcusdc_hourly_gate_v47.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
```

Inputs:

```text
runs/research_v45_btcusdc_enhanced_nested_recency/btcusdc_v43_selector_trades.csv
runs/research_v45_btcusdc_enhanced_nested_recency/btcusdc_v43_validation_trades.csv
```

Outputs:

```text
runs/research_v47_btcusdc_hourly_gate/summary_v47.json
runs/research_v47_btcusdc_hourly_gate/REPORT_V47.md
runs/research_v47_btcusdc_hourly_gate/btcusdc_v47_hourly_gate_summary.csv
```
