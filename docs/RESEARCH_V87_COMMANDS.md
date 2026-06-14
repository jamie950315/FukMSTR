# Research V87 Commands

V87 tests pre-trade repair candidates for the V69 BTCUSDC 12-hour short-term candidate's recent-month deterioration.

```bash
make btcusdc-recent-repair-validation-v87
make test-btcusdc-v87
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

Outputs:

- `runs/research_v87_btcusdc_recent_repair_validation/v87_summary.json`
- `runs/research_v87_btcusdc_recent_repair_validation/v87_repair_candidates.csv`
- `runs/research_v87_btcusdc_recent_repair_validation/v87_selected_recent_months.csv`
- `reports/RESEARCH_V87_BTCUSDC_RECENT_REPAIR_VALIDATION_RESULTS.md`
