# Research V188 Commands

V188 is a BTCUSDC research overlay on top of the V187 selected account path.

It does not add trades, change trade side, or change existing entry thresholds. It only tests a second-layer size step-up inside V187's drought long-base trend bucket.

This is a research candidate, not a live trading guarantee.

## Input

- `runs/research_v187_drought_long_base_trend_stepup/v187_selected_account_path.csv`

If the V187 selected path is missing, the V188 runner will rebuild it through the V187 runner.

## Selected Candidate Rule

- Base path: V187 selected account path.
- Target rows: `source=v122_drought`, `side=long`, `leg=base`, `v187_state_action=drought_long_base_trend_stepup`.
- Emotion rule: `prob_z_30d >= 1.743136`.
- Step-up multiplier: `1.25x` on the existing V187 account return for those rows.

## Run

```bash
make btcusdc-v188-drought-trend-emotion-stepup
```

## Focused Test

```bash
make test-btcusdc-v188
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

- `runs/research_v188_drought_trend_emotion_stepup/v188_policy_comparison.csv`
- `runs/research_v188_drought_trend_emotion_stepup/v188_selected_account_path.csv`
- `runs/research_v188_drought_trend_emotion_stepup/v188_selected_monthly_path.csv`
- `runs/research_v188_drought_trend_emotion_stepup/v188_selected_action_profile.csv`
- `runs/research_v188_drought_trend_emotion_stepup/v188_drought_trend_emotion_stepup_summary.json`
- `reports/RESEARCH_V188_BTCUSDC_DROUGHT_TREND_EMOTION_STEPUP.md`

The `runs/` outputs are local generated artifacts and should not be committed.

## Required Iteration Metrics

Each V188 report must include a V187 vs V188 table with:

- account return estimate;
- improvement in percentage points;
- max drawdown;
- positive months;
- holdout return;
- holdout positive months.

## Promotion Gates

The candidate must:

- improve total return versus V187;
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

V188 is a second-layer sizing overlay inside V187's already narrow drought trend bucket. It treats elevated probability z-score as position-size context, not as a new standalone entry signal.

Forward monitoring and execution validation are still required before any live use.
