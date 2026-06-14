# Research V88 Commands

V88 applies the V87 `oversold_short_veto` repair to the last two years of available BTCUSDC V69 fixed-flow history and checks whether stability is high enough.

```bash
make btcusdc-v87-two-year-stability-v88
make test-btcusdc-v88
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

Outputs:

- `runs/research_v88_btcusdc_v87_two_year_stability/v88_summary.json`
- `runs/research_v88_btcusdc_v87_two_year_stability/v88_two_year_trade_ledger.csv`
- `runs/research_v88_btcusdc_v87_two_year_stability/v88_two_year_months.csv`
- `runs/research_v88_btcusdc_v87_two_year_stability/v88_two_year_quarters.csv`
- `runs/research_v88_btcusdc_v87_two_year_stability/v88_two_year_rolling_windows.csv`
- `reports/RESEARCH_V88_BTCUSDC_V87_TWO_YEAR_STABILITY_RESULTS.md`
