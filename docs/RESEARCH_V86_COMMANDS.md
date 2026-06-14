# Research V86 Commands

V86 validates the V69 BTCUSDC fixed-flow hour-gated candidate as a 12-hour short-term research candidate and separately checks whether the recent edge is still active.

```bash
make btcusdc-short-term-recent-validation-v86
make test-btcusdc-v86
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

Outputs:

- `runs/research_v86_btcusdc_short_term_recent_validation/v86_summary.json`
- `runs/research_v86_btcusdc_short_term_recent_validation/v86_time_windows.csv`
- `runs/research_v86_btcusdc_short_term_recent_validation/v86_months.csv`
- `reports/RESEARCH_V86_BTCUSDC_SHORT_TERM_RECENT_VALIDATION_RESULTS.md`
