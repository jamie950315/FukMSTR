# Research V32-V38 Commands

V32-V38 test BTCUSDC Binance USD-M public `aggTrades` as a richer input than 1m klines. The trades are aggregated to 1-minute bars with taker buy/sell flow features.

```bash
make btcusdc-aggtrade-flow-v32
make btcusdc-aggtrade-flow-rolling-v33
make btcusdc-aggtrade-flow-ytd-rolling-v36
make btcusdc-aggtrade-flow-ytd-oracle-gap-v37
make btcusdc-aggtrade-flow-ytd-prequential-selector-v38
make test-btcusdc-v38
PYTHONPATH=src python -m py_compile src/lob_microprice_lab/*.py scripts/run_btcusdc_aggtrade_flow_v32.py scripts/run_btcusdc_aggtrade_flow_rolling_v33.py scripts/run_btcusdc_aggtrade_flow_ytd_rolling_v36.py scripts/run_btcusdc_aggtrade_flow_ytd_oracle_gap_v37.py scripts/run_btcusdc_aggtrade_flow_ytd_prequential_selector_v38.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
```

Main outputs:

```text
runs/research_v32_btcusdc_aggtrade_flow/
runs/research_v33_btcusdc_aggtrade_flow_rolling/
runs/research_v36_btcusdc_aggtrade_flow_ytd_rolling/
runs/research_v37_btcusdc_aggtrade_flow_ytd_oracle_gap/
runs/research_v38_btcusdc_aggtrade_flow_ytd_prequential_selector/
```
