# Research V176 Commands

V176 tests whether V175's high-confidence long-rescue boost can be combined with fragile-state throttling.

The audit uses the V162 selected BTCUSDC account path and does not add trades, change side, change signal thresholds, or promote live trading.

## Focused Checks

```bash
make test-btcusdc-v176
make btcusdc-v176-combined-state-overlay
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

If the V162 account path is missing, the V176 script rebuilds it through the V162 runner.

## Outputs

```text
runs/research_v176_combined_state_overlay/v176_policy_comparison.csv
runs/research_v176_combined_state_overlay/v176_selected_account_path.csv
runs/research_v176_combined_state_overlay/v176_selected_monthly_path.csv
runs/research_v176_combined_state_overlay/v176_selected_action_profile.csv
runs/research_v176_combined_state_overlay/v176_combined_state_overlay_summary.json
reports/RESEARCH_V176_BTCUSDC_COMBINED_STATE_OVERLAY.md
```

## Selected Policy Family

- Fragile state: long rescue with `funding_z_120d <= -1.5` or `premium_z_30d <= -2.0`.
- Fragile action: scale fragile long rescue trades down to `0.25x`.
- Non-fragile high-confidence state: long rescue, not fragile, and `direction_probability >= 0.64`.
- High-confidence action: scale those trades up to `1.35x`.

## Pass Conditions

Combined candidate:

- Return improvement rate is at least 5%.
- Max drawdown improves by at least 3 percentage points.
- Worst month does not worsen.
- Positive month count does not decline.

This remains a research candidate and is not evidence of future live trading profit.
