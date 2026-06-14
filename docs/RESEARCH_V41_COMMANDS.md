# Research V41 Commands

V41 tests whether 5-second aggTrade bars improve BTCUSDC validation on the V32 independent split.

```bash
make btcusdc-aggtrade-5s-probe-v41
make test-btcusdc-v41
PYTHONPATH=src python -m py_compile src/lob_microprice_lab/*.py scripts/run_btcusdc_aggtrade_5s_probe_v41.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
```

Input:

```text
data/binance_public/binance/um/daily/aggTrades/BTCUSDC/BTCUSDC-aggTrades-2026-05-22.zip
...
data/binance_public/binance/um/daily/aggTrades/BTCUSDC/BTCUSDC-aggTrades-2026-06-10.zip
```

Output:

```text
runs/research_v41_btcusdc_aggtrade_5s_probe/summary_v41.json
runs/research_v41_btcusdc_aggtrade_5s_probe/REPORT_V41.md
```
