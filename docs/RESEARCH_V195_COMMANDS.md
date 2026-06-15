# Research V195 Commands

V195 is a BTCUSDC post-goal overfitting audit for the V192 through V194 historical-improvement sequence.

It does not add trades, change trade side, change thresholds, or promote live trading. It checks whether the recent historical improvements are too concentrated to trust without forward evidence.

This is a research audit, not a live trading guarantee.

## Inputs

- `runs/research_v192_long_base_low_probz_throttle/v192_selected_account_path.csv`
- `runs/research_v193_long_base_top5_premium6h_throttle/v193_selected_account_path.csv`
- `runs/research_v194_long_rescue_premium_discount_stepup/v194_selected_account_path.csv`

## Run

```bash
make btcusdc-v195-post-goal-overfitting-audit
```

## Focused Test

```bash
make test-btcusdc-v195
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

- `runs/research_v195_post_goal_overfitting_audit/v195_version_metrics.csv`
- `runs/research_v195_post_goal_overfitting_audit/v195_overfitting_concentration_table.csv`
- `runs/research_v195_post_goal_overfitting_audit/v195_post_goal_overfitting_audit_summary.json`
- `reports/RESEARCH_V195_BTCUSDC_POST_GOAL_OVERFITTING_AUDIT.md`

The `runs/` outputs are local generated artifacts and should not be committed.

## Required Iteration Metrics

The audit report keeps the required previous-version vs current-version metrics:

- account return estimate;
- improvement in percentage points;
- max drawdown;
- positive months;
- holdout return;
- holdout positive months.

## Audit Gates

The audit raises an overfitting warning when:

- one month contributes more than 50% of an iteration's total improvement;
- one affected trade contributes more than 30% of affected absolute delta;
- affected trades are spread over fewer than 8 active months.

## Interpretation

V195 is intended to stop historical optimization when the improvements become too concentrated. If it flags a warning, V194 should remain an aggressive research candidate, V193 should remain the more conservative comparison, and the next validation step should be forward monitoring on new data.
