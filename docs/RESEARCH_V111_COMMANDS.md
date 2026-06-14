# Research V111 Commands

V111 keeps the V109 MA/price-context/technical ensemble, prioritizes high-confidence predictions, and fills only the minimum required daily fallback trades so every calendar day remains active.

```bash
make test-btcusdc-v111
make btcusdc-high-confidence-daily-fallback-v111
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

Expected outputs:

- `runs/research_v111_btcusdc_high_confidence_daily_fallback/v111_high_confidence_daily_fallback_candidates.csv`
- `runs/research_v111_btcusdc_high_confidence_daily_fallback/v111_high_confidence_daily_fallback_passed_candidates.csv`
- `runs/research_v111_btcusdc_high_confidence_daily_fallback/v111_selector_locked_selected_candidate.csv`
- `runs/research_v111_btcusdc_high_confidence_daily_fallback/v111_summary.json`
- `reports/RESEARCH_V111_BTCUSDC_HIGH_CONFIDENCE_DAILY_FALLBACK_RESULTS.md`
