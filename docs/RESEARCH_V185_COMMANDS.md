# Research V185 Commands

V185 is a BTCUSDC research overlay on top of the V184 selected account path.

It does not add trades, change trade side, or change existing entry thresholds. It only tests whether a narrow long-base high-confidence bucket deserves a size step-up.

This is a research candidate, not a live trading guarantee.

## Input

- `runs/research_v184_long_base_low_premium_throttle/v184_selected_account_path.csv`

If the V184 selected path is missing, the V185 runner will rebuild it through the V184 runner.

## Selected Candidate Rule

- Base path: V184 selected account path.
- Target rows: `side=long`, `leg=base`, `v184_state_action=unchanged`.
- Confidence rule: `direction_probability >= 0.610399`.
- Step-up multiplier: `1.25x` on the existing V184 account return for those rows.

## Run

```bash
make btcusdc-v185-long-base-confidence-stepup
```

## Focused Test

```bash
make test-btcusdc-v185
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

- `runs/research_v185_long_base_confidence_stepup/v185_policy_comparison.csv`
- `runs/research_v185_long_base_confidence_stepup/v185_selected_account_path.csv`
- `runs/research_v185_long_base_confidence_stepup/v185_selected_monthly_path.csv`
- `runs/research_v185_long_base_confidence_stepup/v185_selected_action_profile.csv`
- `runs/research_v185_long_base_confidence_stepup/v185_long_base_confidence_stepup_summary.json`
- `reports/RESEARCH_V185_BTCUSDC_LONG_BASE_CONFIDENCE_STEPUP.md`

The `runs/` outputs are local generated artifacts and should not be committed.

## Promotion Gates

The candidate must:

- improve total return versus V184;
- improve holdout return after `2026-01-01`;
- avoid worse full-path drawdown;
- avoid worse holdout drawdown;
- avoid worse worst-month return;
- avoid reducing the positive-month count;
- have at least 20 step-up trades;
- cover at least 10 active months;
- keep max month trade share at or below 25%;
- keep max single-trade delta share at or below 35%.

## Interpretation

V185 treats direction probability as sizing context for a narrow long-base subset. It is consistent with the recent research pattern: market context is more useful as a throttle or size overlay than as a standalone entry signal.

Forward monitoring and execution validation are still required before any live use.
