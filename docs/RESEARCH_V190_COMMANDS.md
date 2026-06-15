# Research V190 Commands

V190 is a BTCUSDC research overlay on top of the V189 selected account path.

It does not add trades, change trade side, or change existing entry thresholds. It only tests a size step-up inside existing short-base trades after a strong 12-hour prior rally.

This is a research candidate, not a live trading guarantee.

## Input

- `runs/research_v189_rescue_mid_range_extreme_stepup/v189_selected_account_path.csv`

If the V189 selected path is missing, the V190 runner will rebuild it through the V189 runner.

## Selected Candidate Rule

- Base path: V189 selected account path.
- Target rows: `side=short`, `leg=base`, `v188_state_action=unchanged`, `v189_state_action=unchanged`.
- Prior-rally rule: `prior_ret_720_bps >= 138.223233`.
- Step-up multiplier: `1.25x` on the existing V189 account return for those rows.

V190 deliberately avoids rows already modified by V188 or V189.

## Run

```bash
make btcusdc-v190-short-base-prior-rally-stepup
```

## Focused Test

```bash
make test-btcusdc-v190
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

- `runs/research_v190_short_base_prior_rally_stepup/v190_policy_comparison.csv`
- `runs/research_v190_short_base_prior_rally_stepup/v190_selected_account_path.csv`
- `runs/research_v190_short_base_prior_rally_stepup/v190_selected_monthly_path.csv`
- `runs/research_v190_short_base_prior_rally_stepup/v190_selected_action_profile.csv`
- `runs/research_v190_short_base_prior_rally_stepup/v190_short_base_prior_rally_stepup_summary.json`
- `reports/RESEARCH_V190_BTCUSDC_SHORT_BASE_PRIOR_RALLY_STEPUP.md`

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

- improve total return versus V189;
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

V190 treats a strong 12-hour prior rally as sizing context for existing short-base trades. It is not a new standalone short signal.

Forward monitoring and execution validation are still required before any live use.
