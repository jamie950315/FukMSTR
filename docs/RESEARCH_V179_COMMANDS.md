# Research V179 Commands

V179 tests whether market trend/emotion is more useful as a short-side sizing filter than as a direct signal.

## Run

```bash
make test-btcusdc-v179
make btcusdc-v179-short-nonspike-overlay
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Inputs

```text
runs/research_v178_diversified_overlay/v178_selected_account_path.csv
```

If the V178 input does not exist, the V179 script regenerates V178 first.

## Outputs

```text
runs/research_v179_short_nonspike_overlay/v179_policy_comparison.csv
runs/research_v179_short_nonspike_overlay/v179_selected_account_path.csv
runs/research_v179_short_nonspike_overlay/v179_selected_monthly_path.csv
runs/research_v179_short_nonspike_overlay/v179_selected_action_profile.csv
runs/research_v179_short_nonspike_overlay/v179_short_nonspike_overlay_summary.json
reports/RESEARCH_V179_BTCUSDC_SHORT_NON_SPIKE_OVERLAY.md
```

## Selected Rule

- Base path: V178 selected account path.
- V179 only scales existing short trades after the V178 long-rescue overlay.
- Selected boost state: short trade with `prob_vs_day_sofar_max <= 0.01`.
- Selected multiplier: `1.25x`.
- V179 does not add trades, change side, change thresholds, or promote live trading.

## Pass Criteria

- Return delta vs V178 must be positive and at least 5 pct.
- Full-path max drawdown must not worsen.
- Worst month must not worsen.
- Holdout return and holdout drawdown must not worsen.
- Boosted trade count must be at least 40.
- Boosted active months must be at least 12.
- Max single-month boost share must be at most 25%.

This remains a research audit, not a live trading guarantee.
