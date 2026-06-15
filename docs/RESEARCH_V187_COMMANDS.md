# Research V187 Commands

V187 is a BTCUSDC research overlay on top of the V186 selected account path.

It does not add trades, change trade side, or change existing entry thresholds. It only tests whether a narrow drought long-base bucket deserves a size step-up after deeper 60-minute extension.

This is a research candidate, not a live trading guarantee.

## Input

- `runs/research_v186_long_rescue_day_sofar_stepup/v186_selected_account_path.csv`

If the V186 selected path is missing, the V187 runner will rebuild it through the V186 runner.

## Selected Candidate Rule

- Base path: V186 selected account path.
- Target rows: `source=v122_drought`, `side=long`, `leg=base`, `v186_state_action=unchanged`.
- Trend rule: `trend_abs_60_bps >= 238.049377`.
- Step-up multiplier: `1.25x` on the existing V186 account return for those rows.

## Run

```bash
make btcusdc-v187-drought-long-base-trend-stepup
```

## Focused Test

```bash
make test-btcusdc-v187
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

- `runs/research_v187_drought_long_base_trend_stepup/v187_policy_comparison.csv`
- `runs/research_v187_drought_long_base_trend_stepup/v187_selected_account_path.csv`
- `runs/research_v187_drought_long_base_trend_stepup/v187_selected_monthly_path.csv`
- `runs/research_v187_drought_long_base_trend_stepup/v187_selected_action_profile.csv`
- `runs/research_v187_drought_long_base_trend_stepup/v187_drought_long_base_trend_stepup_summary.json`
- `reports/RESEARCH_V187_BTCUSDC_DROUGHT_LONG_BASE_TREND_STEPUP.md`

The `runs/` outputs are local generated artifacts and should not be committed.

## Required Iteration Metrics

Each V187 report must include a V186 vs V187 table with:

- account return estimate;
- improvement in percentage points;
- max drawdown;
- positive months;
- holdout return;
- holdout positive months.

## Promotion Gates

The candidate must:

- improve total return versus V186;
- improve holdout return after `2026-01-01`;
- avoid worse full-path drawdown, allowing only tiny floating-point noise;
- avoid worse holdout drawdown, allowing only tiny floating-point noise;
- avoid worse worst-month return;
- avoid reducing the positive-month count;
- avoid reducing the holdout positive-month count;
- have at least 15 step-up trades;
- cover at least 9 active months;
- keep max month trade share at or below 30%;
- keep max single-trade delta share at or below 30%.

## Interpretation

V187 finds that a drought long-base subset behaves better after deeper 60-minute extension. It treats that extension as position-size context for an existing signal family, not as a standalone entry signal.

Forward monitoring and execution validation are still required before any live use.
