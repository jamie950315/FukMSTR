# Research V112 BTCUSDC Expanded Top-K Daily Fallback Commands

V112 keeps the V111 feature-family ensemble and exact-daily fallback structure, then expands the selector-only daily top-k search from 5 to 10. The locked candidate must pass the existing exact-daily stability gate and improve V111 holdout PnL by at least 5%.

## Run

```bash
make btcusdc-expanded-topk-daily-fallback-v112
```

## Focused Tests

```bash
make test-btcusdc-v112
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

- `runs/research_v112_btcusdc_expanded_topk_daily_fallback/v112_expanded_topk_daily_fallback_candidates.csv`
- `runs/research_v112_btcusdc_expanded_topk_daily_fallback/v112_expanded_topk_daily_fallback_passed_candidates.csv`
- `runs/research_v112_btcusdc_expanded_topk_daily_fallback/v112_selector_locked_selected_candidate.csv`
- `runs/research_v112_btcusdc_expanded_topk_daily_fallback/v112_summary.json`
- `reports/RESEARCH_V112_BTCUSDC_EXPANDED_TOPK_DAILY_FALLBACK_RESULTS.md`
