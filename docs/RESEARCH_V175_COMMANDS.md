# Research V175 Commands

V175 tests whether the V174 market-state evidence is more useful as a long-rescue sizing overlay than as a direct entry signal.

The audit uses the V162 selected BTCUSDC account path and does not add trades, change side, change signal thresholds, or promote live trading.

## Focused Checks

```bash
make test-btcusdc-v175
make btcusdc-v175-long-rescue-state-overlay
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

If the V162 account path is missing, the V175 script rebuilds it through the V162 runner.

## Outputs

```text
runs/research_v175_long_rescue_state_overlay/v175_policy_comparison.csv
runs/research_v175_long_rescue_state_overlay/v175_selected_account_path.csv
runs/research_v175_long_rescue_state_overlay/v175_selected_monthly_path.csv
runs/research_v175_long_rescue_state_overlay/v175_selected_action_profile.csv
runs/research_v175_long_rescue_state_overlay/v175_long_rescue_state_overlay_summary.json
reports/RESEARCH_V175_BTCUSDC_LONG_RESCUE_STATE_OVERLAY.md
```

## Policy Family

- Baseline: V162 account path with no overlay.
- Fragile funding throttle: scale existing long rescue trades when `funding_z_120d <= -1.5`.
- Non-fragile high-confidence boost: scale existing long rescue trades when `funding_z_120d > -1.5` and `direction_probability >= 0.62`.
- Balanced variants combine fragile-state throttling and non-fragile high-confidence boosting.

## Pass Conditions

Growth candidate:

- Return improvement rate is at least 5%.
- Max drawdown does not worsen.
- Worst month does not worsen.
- Positive month count does not decline.

Balanced candidate:

- Total return improves.
- Max drawdown improves by at least 3 percentage points.
- Worst month does not worsen.
- Positive month count does not decline.

This remains a research candidate and is not evidence of future live trading profit.
