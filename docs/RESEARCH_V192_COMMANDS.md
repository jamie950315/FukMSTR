# Research V192 Commands

V192 is a BTCUSDC research overlay on top of the V191 selected account path.

It does not add trades, change trade side, or change existing entry thresholds. It only tests a size throttle inside a remaining long-base coverage bucket when the 7-day probability z-score is low.

This is a research candidate, not a live trading guarantee.

## Input

- `runs/research_v191_long_base_prior_range_stepup/v191_selected_account_path.csv`

If the V191 selected path is missing, the V192 runner will rebuild it through the V191 runner.

## Selected Candidate Rule

- Base path: V191 selected account path.
- Target rows: `indicator_key=v125_top7_lb14_coverage`, `side=long`, `leg=base`, `v188_state_action=unchanged`, `v189_state_action=unchanged`, `v190_state_action=unchanged`, `v191_state_action=unchanged`.
- Probability-z rule: `prob_z_7d <= 2.339038`.
- Throttle multiplier: `0.50x` on the existing V191 account return for those rows.

V192 deliberately avoids rows already modified by V188, V189, V190, or V191.

## Run

```bash
make btcusdc-v192-long-base-low-probz-throttle
```

## Focused Test

```bash
make test-btcusdc-v192
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

- `runs/research_v192_long_base_low_probz_throttle/v192_policy_comparison.csv`
- `runs/research_v192_long_base_low_probz_throttle/v192_selected_account_path.csv`
- `runs/research_v192_long_base_low_probz_throttle/v192_selected_monthly_path.csv`
- `runs/research_v192_long_base_low_probz_throttle/v192_selected_action_profile.csv`
- `runs/research_v192_long_base_low_probz_throttle/v192_long_base_low_probz_throttle_summary.json`
- `reports/RESEARCH_V192_BTCUSDC_LONG_BASE_LOW_PROBZ_THROTTLE.md`

The `runs/` outputs are local generated artifacts and should not be committed.

## Required Iteration Metrics

Every iteration report must include the previous-version vs current-version table with:

- account return estimate;
- improvement in percentage points;
- max drawdown;
- positive months;
- holdout return;
- holdout positive months.

## Promotion Gates

The candidate must:

- improve total return versus V191;
- improve holdout return after `2026-01-01`;
- avoid worse full-path drawdown, allowing only tiny floating-point noise;
- avoid worse holdout drawdown, allowing only tiny floating-point noise;
- avoid worse worst-month return;
- avoid reducing the positive-month count;
- avoid reducing the holdout positive-month count;
- have at least 15 throttle trades;
- cover at least 8 active months;
- keep max month trade share at or below 35%;
- keep max single-trade delta share at or below 35%.

## Interpretation

V192 treats low 7-day probability z-score as risk context for a remaining long-base coverage bucket. It reduces size only and is not a new standalone entry or exit signal.

Forward monitoring and execution validation are still required before any live use.
