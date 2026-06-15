# Research V191 Commands

V191 is a BTCUSDC research overlay on top of the V190 selected account path.

It does not add trades, change trade side, or change existing entry thresholds. It only tests a size step-up inside existing long-base trades when the 24-hour prior range position is above the selected floor.

This is a research candidate, not a live trading guarantee.

## Input

- `runs/research_v190_short_base_prior_rally_stepup/v190_selected_account_path.csv`

If the V190 selected path is missing, the V191 runner will rebuild it through the V190 runner.

## Selected Candidate Rule

- Base path: V190 selected account path.
- Target rows: `side=long`, `leg=base`, `v188_state_action=unchanged`, `v189_state_action=unchanged`, `v190_state_action=unchanged`.
- Prior-range rule: `prior_range_pos_1440 >= 0.326636`.
- Step-up multiplier: `1.25x` on the existing V190 account return for those rows.

V191 deliberately avoids rows already modified by V188, V189, or V190.

## Run

```bash
make btcusdc-v191-long-base-prior-range-stepup
```

## Focused Test

```bash
make test-btcusdc-v191
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

- `runs/research_v191_long_base_prior_range_stepup/v191_policy_comparison.csv`
- `runs/research_v191_long_base_prior_range_stepup/v191_selected_account_path.csv`
- `runs/research_v191_long_base_prior_range_stepup/v191_selected_monthly_path.csv`
- `runs/research_v191_long_base_prior_range_stepup/v191_selected_action_profile.csv`
- `runs/research_v191_long_base_prior_range_stepup/v191_long_base_prior_range_stepup_summary.json`
- `reports/RESEARCH_V191_BTCUSDC_LONG_BASE_PRIOR_RANGE_STEPUP.md`

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

- improve total return versus V190;
- improve holdout return after `2026-01-01`;
- avoid worse full-path drawdown, allowing only tiny floating-point noise;
- avoid worse holdout drawdown, allowing only tiny floating-point noise;
- avoid worse worst-month return;
- avoid reducing the positive-month count;
- avoid reducing the holdout positive-month count;
- have at least 15 step-up trades;
- cover at least 8 active months;
- keep max month trade share at or below 35%;
- keep max single-trade delta share at or below 35%.

## Interpretation

V191 treats the 24-hour prior range position as sizing context for existing long-base trades. It is not a new standalone long signal.

Forward monitoring and execution validation are still required before any live use.
