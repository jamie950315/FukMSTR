# Research V161 Commands

V161 tests a small sizing boost for low `day_sofar_count` trades on top of the promoted V160 account path. It is a sizing adjustment only, not a new entry signal.

## Focused Test

```bash
make test-btcusdc-v161
```

## Run V161

```bash
make btcusdc-v161-day-sofar-count-boost
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

```text
runs/research_v161_day_sofar_count_boost/v161_selected_account_path.csv
runs/research_v161_day_sofar_count_boost/v161_day_sofar_count_boost_candidate.csv
runs/research_v161_day_sofar_count_boost/v161_monthly_account_return.csv
runs/research_v161_day_sofar_count_boost/v161_day_sofar_count_context_metrics.csv
runs/research_v161_day_sofar_count_boost/v161_day_sofar_count_boost_summary.json
reports/RESEARCH_V161_BTCUSDC_DAY_SOFAR_COUNT_BOOST.md
```

## Research Notes

- Base: V160 selected account path.
- Feature: `day_sofar_count`.
- Segment: `all`.
- Threshold: selector q0.30.
- Operator: `<=`.
- Modifier: additional `1.05x` on flagged trades.
- No new trades are added.
- Existing trade sides are not changed.
- Holdout is used only for validation.
- This is a research candidate, not a live trading guarantee.
