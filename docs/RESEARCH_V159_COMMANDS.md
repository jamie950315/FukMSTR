# Research V159 Commands

V159 promotes the best post-V158 strict-gate candidate found in the continuation scan: a base-trade absolute 1440-minute trend boost on top of V158.

## Focused Test

```bash
make test-btcusdc-v159
```

## Run V159

```bash
make btcusdc-v159-base-trend-abs-boost
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

```text
runs/research_v159_base_trend_abs_boost/v159_selected_account_path.csv
runs/research_v159_base_trend_abs_boost/v159_base_trend_abs_boost_candidate.csv
runs/research_v159_base_trend_abs_boost/v159_monthly_account_return.csv
runs/research_v159_base_trend_abs_boost/v159_base_trend_abs_context_metrics.csv
runs/research_v159_base_trend_abs_boost/v159_base_trend_abs_boost_summary.json
reports/RESEARCH_V159_BTCUSDC_BASE_TREND_ABS_BOOST.md
```

## Research Notes

- Base: V158 selected account path.
- Feature: `trend_abs_1440_bps`.
- Segment: `base`.
- Rule: `trend_abs_1440_bps >= selector q0.80`.
- Modifier: `1.10x`.
- Thresholds use selector-period data only.
- Holdout is used only for validation.
- This is a research candidate, not a live trading guarantee.
