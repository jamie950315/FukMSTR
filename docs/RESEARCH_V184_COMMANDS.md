# Research V184 Commands

V184 tests whether depressed premium long-base rows should have reduced exposure after the V183 short-base momentum step-up.

## Run

```bash
make test-btcusdc-v184
make btcusdc-v184-long-base-low-premium-throttle
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Inputs

```text
runs/research_v183_short_base_momentum_stepup/v183_selected_account_path.csv
```

If the V183 input does not exist, the V184 script regenerates V183 first.

## Outputs

```text
runs/research_v184_long_base_low_premium_throttle/v184_policy_comparison.csv
runs/research_v184_long_base_low_premium_throttle/v184_selected_account_path.csv
runs/research_v184_long_base_low_premium_throttle/v184_selected_monthly_path.csv
runs/research_v184_long_base_low_premium_throttle/v184_selected_action_profile.csv
runs/research_v184_long_base_low_premium_throttle/v184_long_base_low_premium_throttle_summary.json
reports/RESEARCH_V184_BTCUSDC_LONG_BASE_LOW_PREMIUM_THROTTLE.md
```

## Selected Rule

- Base path: V183 selected account path.
- V184 only changes rows with `side=long`, `leg=base`, and `v183_state_action=unchanged`.
- Selected low-premium rule: `premium_z_120d <= -1.829957`.
- Selected multiplier: `0.00x`.
- V184 does not add trades, change side, change thresholds, or promote live trading.

## Pass Criteria

- Return delta vs V183 must be at least 10 pct.
- Holdout return delta vs V183 must be at least 5 pct.
- Full-path and holdout max drawdown must not worsen.
- Worst month must not worsen.
- Positive month count must not decline.
- Throttled trade count must be at least 20.
- Throttled active months must be at least 8.
- Max single-month throttled trade share must be at most 30%.
- Max single-trade delta contribution must be at most 35%.

This remains a research audit, not a live trading guarantee.
