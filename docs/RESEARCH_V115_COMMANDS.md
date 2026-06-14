# Research V115 Commands

V115 applies a contrarian sizing overlay on the locked V114 BTCUSDC trade ledger.

```bash
make btcusdc-v112-contrarian-sizing-v115
make test-btcusdc-v115
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

Main output:

```text
reports/RESEARCH_V115_BTCUSDC_V112_CONTRARIAN_SIZING_RESULTS.md
runs/research_v115_btcusdc_v112_contrarian_sizing/v115_summary.json
runs/research_v115_btcusdc_v112_contrarian_sizing/v115_months.csv
runs/research_v115_btcusdc_v112_contrarian_sizing/v115_weighted_trade_ledger.csv
```
