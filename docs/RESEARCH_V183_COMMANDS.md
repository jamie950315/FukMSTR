# Research V183 Commands

V183 tests whether the V182 short-base momentum bucket deserves a second-step sizing increase.

## Run

```bash
make test-btcusdc-v183
make btcusdc-v183-short-base-momentum-stepup
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Inputs

```text
runs/research_v182_short_base_momentum_boost/v182_selected_account_path.csv
```

If the V182 input does not exist, the V183 script regenerates V182 first.

## Outputs

```text
runs/research_v183_short_base_momentum_stepup/v183_policy_comparison.csv
runs/research_v183_short_base_momentum_stepup/v183_selected_account_path.csv
runs/research_v183_short_base_momentum_stepup/v183_selected_monthly_path.csv
runs/research_v183_short_base_momentum_stepup/v183_selected_action_profile.csv
runs/research_v183_short_base_momentum_stepup/v183_short_base_momentum_stepup_summary.json
reports/RESEARCH_V183_BTCUSDC_SHORT_BASE_MOMENTUM_STEPUP.md
```

## Selected Rule

- Base path: V182 selected account path.
- V183 only changes rows already marked by V182 as `short_base_momentum_boost`.
- Selected multiplier: `1.25x` on top of the V182 account return for that existing bucket.
- V183 does not add trades, change side, change thresholds, or promote live trading.
- The high-return long-rescue emotion candidate remains research-only and is rejected unless it passes sample and concentration gates.

## Pass Criteria

- Return delta vs V182 must be at least 10 pct.
- Holdout return delta vs V182 must be at least 5 pct.
- Full-path and holdout max drawdown must not worsen.
- Worst month must not worsen.
- Positive month count must not decline.
- Step-up trade count must be at least 30.
- Step-up active months must be at least 10.
- Max single-month step-up trade share must be at most 25%.
- Max single-trade delta contribution must be at most 35%.

This remains a research audit, not a live trading guarantee.
