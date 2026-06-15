# Research V194 Commands

V194 is a BTCUSDC research overlay on top of the V193 selected account path.

It does not add trades, change trade side, or change existing entry thresholds. It only tests a size step-up inside remaining long-rescue trades when the premium open is negative enough.

This is a research candidate, not a live trading guarantee.

## Input

- `runs/research_v193_long_base_top5_premium6h_throttle/v193_selected_account_path.csv`

If the V193 selected path is missing, the V194 runner will rebuild it through the V193 runner.

## Selected Candidate Rule

- Base path: V193 selected account path.
- Target rows: `side=long`, `leg=rescue`, `v188_state_action=unchanged`, `v189_state_action=unchanged`, `v190_state_action=unchanged`, `v191_state_action=unchanged`, `v192_state_action=unchanged`, `v193_state_action=unchanged`.
- Premium-open rule: `premium_open <= -0.000351`.
- Step-up multiplier: `1.25x` on the existing V193 account return for those rows.

V194 deliberately avoids rows already modified by V188, V189, V190, V191, V192, or V193.

## Run

```bash
make btcusdc-v194-long-rescue-premium-discount-stepup
```

## Focused Test

```bash
make test-btcusdc-v194
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

- `runs/research_v194_long_rescue_premium_discount_stepup/v194_policy_comparison.csv`
- `runs/research_v194_long_rescue_premium_discount_stepup/v194_selected_account_path.csv`
- `runs/research_v194_long_rescue_premium_discount_stepup/v194_selected_monthly_path.csv`
- `runs/research_v194_long_rescue_premium_discount_stepup/v194_selected_action_profile.csv`
- `runs/research_v194_long_rescue_premium_discount_stepup/v194_long_rescue_premium_discount_stepup_summary.json`
- `reports/RESEARCH_V194_BTCUSDC_LONG_RESCUE_PREMIUM_DISCOUNT_STEPUP.md`

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

- improve total return versus V193;
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

V194 treats a negative premium open as supportive context for remaining long-rescue trades. It increases size only and is not a new standalone entry or exit signal.

Forward monitoring and execution validation are still required before any live use.
