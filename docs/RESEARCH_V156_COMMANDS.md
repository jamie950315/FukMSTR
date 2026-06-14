# Research V156 Commands

V156 tests a narrow sizing step on top of V155. It does not add entries, change sides, or derive a new threshold from holdout data.

## Focused Test

```bash
make test-btcusdc-v156
```

## Run V156

```bash
make btcusdc-v156-base-long-premium-stepup
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

```text
runs/research_v156_base_long_premium_stepup/v156_selected_account_path.csv
runs/research_v156_base_long_premium_stepup/v156_base_long_premium_stepup_candidate.csv
runs/research_v156_base_long_premium_stepup/v156_monthly_account_return.csv
runs/research_v156_base_long_premium_stepup/v156_base_long_premium_context_metrics.csv
runs/research_v156_base_long_premium_stepup/v156_base_long_premium_stepup_summary.json
reports/RESEARCH_V156_BTCUSDC_BASE_LONG_PREMIUM_STEPUP.md
```

## Research Notes

- Base: V155 selected account path.
- Source flag: `v155_base_long_premium_flag`.
- V155 total sizing: `1.075x`.
- V156 total sizing: `1.10x`.
- The incremental multiplier is applied only to trades already flagged by V155.
- This is a research candidate, not a live trading guarantee.
