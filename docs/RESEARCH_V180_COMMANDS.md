# Research V180 Commands

V180 tests whether the remaining weak short-base regime after V179 should be throttled when same-day signal activity is already elevated.

## Run

```bash
make test-btcusdc-v180
make btcusdc-v180-short-base-late-day-throttle
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Inputs

```text
runs/research_v179_short_nonspike_overlay/v179_selected_account_path.csv
```

If the V179 input does not exist, the V180 script regenerates V179 first.

## Outputs

```text
runs/research_v180_short_base_late_day_throttle/v180_policy_comparison.csv
runs/research_v180_short_base_late_day_throttle/v180_selected_account_path.csv
runs/research_v180_short_base_late_day_throttle/v180_selected_monthly_path.csv
runs/research_v180_short_base_late_day_throttle/v180_selected_action_profile.csv
runs/research_v180_short_base_late_day_throttle/v180_short_base_late_day_throttle_summary.json
reports/RESEARCH_V180_BTCUSDC_SHORT_BASE_LATE_DAY_THROTTLE.md
```

## Selected Rule

- Base path: V179 selected account path.
- V180 only scales existing short base trades that V179 left unchanged.
- Selected throttle state: `day_sofar_count >= 5`.
- Selected multiplier: `0.25x`.
- V180 does not add trades, change side, change thresholds, or promote live trading.

## Pass Criteria

- Return delta vs V179 must be at least 10 pct.
- Full-path max drawdown must not worsen.
- Worst month must not worsen.
- Holdout return and holdout drawdown must not worsen.
- Throttled trade count must be at least 40.
- Throttled active months must be at least 12.
- Max single-month throttle share must be at most 25%.

This remains a research audit, not a live trading guarantee.
