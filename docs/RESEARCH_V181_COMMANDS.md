# Research V181 Commands

V181 tests whether the V180 late-day short-base risk bucket should be fully de-risked instead of kept at 0.25x exposure.

## Run

```bash
make test-btcusdc-v181
make btcusdc-v181-late-day-hard-throttle
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Inputs

```text
runs/research_v180_short_base_late_day_throttle/v180_selected_account_path.csv
```

If the V180 input does not exist, the V181 script regenerates V180 first.

## Outputs

```text
runs/research_v181_late_day_hard_throttle/v181_policy_comparison.csv
runs/research_v181_late_day_hard_throttle/v181_selected_account_path.csv
runs/research_v181_late_day_hard_throttle/v181_selected_monthly_path.csv
runs/research_v181_late_day_hard_throttle/v181_selected_action_profile.csv
runs/research_v181_late_day_hard_throttle/v181_late_day_hard_throttle_summary.json
reports/RESEARCH_V181_BTCUSDC_LATE_DAY_HARD_THROTTLE.md
```

## Selected Rule

- Base path: V180 selected account path.
- V181 only changes rows already marked by V180 as `short_base_late_day_throttle`.
- Selected hard throttle state: V180 late-day short-base throttle rows.
- Selected multiplier: `0.00x`.
- V181 does not add trades, change side, change thresholds, or promote live trading.

## Pass Criteria

- Return delta vs V180 must be at least 5 pct.
- Full-path max drawdown must not worsen.
- Worst month must not worsen.
- Holdout return and holdout drawdown must not worsen.
- Hard-throttled trade count must be at least 40.
- Hard-throttled active months must be at least 12.
- Max single-month hard-throttle share must be at most 25%.

This remains a research audit, not a live trading guarantee.
