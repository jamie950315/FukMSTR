# Research V160 Commands

V160 tests a small additional step-up on the already-promoted V159 base trend-abs flag. It is a sizing adjustment only, not a new entry signal.

## Focused Test

```bash
make test-btcusdc-v160
```

## Run V160

```bash
make btcusdc-v160-base-trend-abs-stepup
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

```text
runs/research_v160_base_trend_abs_stepup/v160_selected_account_path.csv
runs/research_v160_base_trend_abs_stepup/v160_base_trend_abs_stepup_candidate.csv
runs/research_v160_base_trend_abs_stepup/v160_monthly_account_return.csv
runs/research_v160_base_trend_abs_stepup/v160_base_trend_abs_context_metrics.csv
runs/research_v160_base_trend_abs_stepup/v160_base_trend_abs_stepup_summary.json
reports/RESEARCH_V160_BTCUSDC_BASE_TREND_ABS_STEPUP.md
```

## Research Notes

- Base: V159 selected account path.
- Source flag: `v159_base_trend_abs_boost_flag`.
- Modifier: additional `1.05x` on flagged trades.
- No new threshold is set.
- Holdout is used only for validation.
- This is a research candidate, not a live trading guarantee.
