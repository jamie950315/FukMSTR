# Research V189 Commands

V189 is a BTCUSDC research overlay on top of the V188 selected account path.

It does not add trades, change trade side, or change existing entry thresholds. It only tests a size step-up inside the independent long-rescue mid-confidence bucket when the 120-minute range-extreme context is high.

This is a research candidate, not a live trading guarantee.

## Input

- `runs/research_v188_drought_trend_emotion_stepup/v188_selected_account_path.csv`

If the V188 selected path is missing, the V189 runner will rebuild it through the V188 runner.

## Selected Candidate Rule

- Base path: V188 selected account path.
- Target rows: `indicator_key=rescue_mid_0p62_0p66`, `side=long`, `leg=rescue`, `v188_state_action=unchanged`.
- Range rule: `range_extreme_120 >= 0.807460`.
- Step-up multiplier: `1.25x` on the existing V188 account return for those rows.

V189 deliberately avoids adding another layer inside the narrow V188 drought trend emotion bucket.

## Run

```bash
make btcusdc-v189-rescue-mid-range-extreme-stepup
```

## Focused Test

```bash
make test-btcusdc-v189
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

- `runs/research_v189_rescue_mid_range_extreme_stepup/v189_policy_comparison.csv`
- `runs/research_v189_rescue_mid_range_extreme_stepup/v189_selected_account_path.csv`
- `runs/research_v189_rescue_mid_range_extreme_stepup/v189_selected_monthly_path.csv`
- `runs/research_v189_rescue_mid_range_extreme_stepup/v189_selected_action_profile.csv`
- `runs/research_v189_rescue_mid_range_extreme_stepup/v189_rescue_mid_range_extreme_stepup_summary.json`
- `reports/RESEARCH_V189_BTCUSDC_RESCUE_MID_RANGE_EXTREME_STEPUP.md`

The `runs/` outputs are local generated artifacts and should not be committed.

## Required Iteration Metrics

Every iteration report from V189 onward must include the previous-version vs current-version table with:

- account return estimate;
- improvement in percentage points;
- max drawdown;
- positive months;
- holdout return;
- holdout positive months.

## Promotion Gates

The candidate must:

- improve total return versus V188;
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

V189 treats the 120-minute range-extreme condition as a sizing context for existing long rescue mid-confidence trades. It is not a new standalone entry signal.

Forward monitoring and execution validation are still required before any live use.
