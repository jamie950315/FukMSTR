# Research V178 Commands

V178 responds to the V177 warning by searching for a broader and more month-diversified long-rescue sizing overlay.

The audit uses the V162 selected BTCUSDC account path and does not add trades, change side, change signal thresholds, or promote live trading.

## Focused Checks

```bash
make test-btcusdc-v178
make btcusdc-v178-diversified-overlay
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Inputs

```text
runs/research_v162_long_trend_follow_boost/v162_selected_account_path.csv
```

If the V162 account path is missing, the V178 script rebuilds it through the V162 runner.

## Outputs

```text
runs/research_v178_diversified_overlay/v178_policy_comparison.csv
runs/research_v178_diversified_overlay/v178_selected_account_path.csv
runs/research_v178_diversified_overlay/v178_selected_monthly_path.csv
runs/research_v178_diversified_overlay/v178_selected_action_profile.csv
runs/research_v178_diversified_overlay/v178_diversified_overlay_summary.json
reports/RESEARCH_V178_BTCUSDC_DIVERSIFIED_OVERLAY.md
```

## Selected Policy Family

- Fragile state: long rescue with `funding_z_120d <= -1.5` or `premium_z_30d <= -2.0`.
- Fragile action: scale fragile long rescue trades to `0.50x`.
- Diversified boost state: long rescue, not fragile, `direction_probability >= 0.61`, and `prior_range_pos_720 >= 0.005`.
- Boost action: scale diversified boost trades to `1.25x`.

## Pass Conditions

Diversified candidate:

- Return improvement rate is at least 3%.
- Max drawdown does not worsen.
- Worst month does not worsen.
- Positive month count does not decline.
- Holdout return delta is non-negative.
- Boosted trade count is at least 20.
- No single month contains more than 40% of boosted trades.

This remains a research candidate and is not evidence of future live trading profit.
