# Research V186 Commands

V186 is a BTCUSDC research overlay on top of the V185 selected account path.

It does not add trades, change trade side, or change existing entry thresholds. It only tests whether a narrow long-rescue bucket that fires earlier in the day deserves a size step-up.

This is a research candidate, not a live trading guarantee.

## Input

- `runs/research_v185_long_base_confidence_stepup/v185_selected_account_path.csv`

If the V185 selected path is missing, the V186 runner will rebuild it through the V185 runner.

## Selected Candidate Rule

- Base path: V185 selected account path.
- Target rows: `side=long`, `leg=rescue`, `v185_state_action=unchanged`.
- Day-sofar rule: `day_sofar_count <= 200.75`.
- Step-up multiplier: `1.25x` on the existing V185 account return for those rows.

## Run

```bash
make btcusdc-v186-long-rescue-day-sofar-stepup
```

## Focused Test

```bash
make test-btcusdc-v186
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

- `runs/research_v186_long_rescue_day_sofar_stepup/v186_policy_comparison.csv`
- `runs/research_v186_long_rescue_day_sofar_stepup/v186_selected_account_path.csv`
- `runs/research_v186_long_rescue_day_sofar_stepup/v186_selected_monthly_path.csv`
- `runs/research_v186_long_rescue_day_sofar_stepup/v186_selected_action_profile.csv`
- `runs/research_v186_long_rescue_day_sofar_stepup/v186_long_rescue_day_sofar_stepup_summary.json`
- `reports/RESEARCH_V186_BTCUSDC_LONG_RESCUE_DAY_SOFAR_STEPUP.md`

The `runs/` outputs are local generated artifacts and should not be committed.

## Required Iteration Metrics

Each V186 report must include a V185 vs V186 table with:

- account return estimate;
- improvement in percentage points;
- max drawdown;
- positive months;
- holdout return;
- holdout positive months.

## Promotion Gates

The candidate must:

- improve total return versus V185;
- improve holdout return after `2026-01-01`;
- avoid worse full-path drawdown;
- avoid worse holdout drawdown;
- avoid worse worst-month return;
- avoid reducing the positive-month count;
- avoid reducing the holdout positive-month count;
- have at least 20 step-up trades;
- cover at least 7 active months;
- keep max month trade share at or below 35%;
- keep max single-trade delta share at or below 35%.

## Interpretation

V186 extends the sizing-overlay pattern from V185 into long-rescue trades. It treats day-sofar count as context for position size, not as a standalone entry signal.

Forward monitoring and execution validation are still required before any live use.
