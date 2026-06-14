# Research V158 Commands

V158 promotes the best strict-gate candidate found by V157: a base-trade range-position boost on top of V156.

## Focused Test

```bash
make test-btcusdc-v158
```

## Run V158

```bash
make btcusdc-v158-base-range-position-boost
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

```text
runs/research_v158_base_range_position_boost/v158_selected_account_path.csv
runs/research_v158_base_range_position_boost/v158_base_range_position_boost_candidate.csv
runs/research_v158_base_range_position_boost/v158_monthly_account_return.csv
runs/research_v158_base_range_position_boost/v158_base_range_position_context_metrics.csv
runs/research_v158_base_range_position_boost/v158_base_range_position_boost_summary.json
reports/RESEARCH_V158_BTCUSDC_BASE_RANGE_POSITION_BOOST.md
```

## Research Notes

- Base: V156 selected account path.
- Feature: `prior_range_pos_1440`.
- Segment: `base`.
- Rule: `prior_range_pos_1440 >= selector q0.60`.
- Modifier: `1.10x`.
- Thresholds use selector-period data only.
- Holdout is used only for validation.
- This is a research candidate, not a live trading guarantee.
