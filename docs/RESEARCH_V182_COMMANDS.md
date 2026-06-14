# Research V182 Commands

V182 tests whether V181 unchanged short-base rows with elevated 720-minute trend magnitude deserve a modest sizing boost.

## Run

```bash
make test-btcusdc-v182
make btcusdc-v182-short-base-momentum-boost
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Inputs

```text
runs/research_v181_late_day_hard_throttle/v181_selected_account_path.csv
```

If the V181 input does not exist, the V182 script regenerates V181 first.

## Outputs

```text
runs/research_v182_short_base_momentum_boost/v182_policy_comparison.csv
runs/research_v182_short_base_momentum_boost/v182_selected_account_path.csv
runs/research_v182_short_base_momentum_boost/v182_selected_monthly_path.csv
runs/research_v182_short_base_momentum_boost/v182_selected_action_profile.csv
runs/research_v182_short_base_momentum_boost/v182_short_base_momentum_boost_summary.json
reports/RESEARCH_V182_BTCUSDC_SHORT_BASE_MOMENTUM_BOOST.md
```

## Selected Rule

- Base path: V181 selected account path.
- V182 only changes rows already left unchanged by V181.
- Selected boosted rows must have `side=short`, `leg=base`, and `trend_abs_720_bps >= 250`.
- Selected multiplier: `1.25x`.
- V182 does not add trades, change side, change thresholds, or promote live trading.

## Pass Criteria

- Return delta vs V181 must be at least 10 pct.
- Holdout return delta vs V181 must be at least 5 pct.
- Full-path and holdout max drawdown must not worsen.
- Worst month must not worsen.
- Positive month count must not decline.
- Boosted trade count must be at least 30.
- Boosted active months must be at least 10.
- Max single-month boosted trade share must be at most 25%.

This remains a research audit, not a live trading guarantee.
