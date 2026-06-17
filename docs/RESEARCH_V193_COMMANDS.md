# Research V193 Commands

V193 is the official BTCUSDC online/paper iteration for monitoring and historical replay.

It started as a BTCUSDC research overlay on top of the V192 selected account path and is now the promoted online/paper iteration recorded in `configs/btcusdc_v223_promoted_strategy_manifest.json`.

It does not add trades, change trade side, or change existing entry thresholds. It only tests a size throttle inside a remaining `v125_top5_lb14_strict` long-base bucket when the 6-hour premium is not sufficiently negative.

This is a research candidate, not a live trading guarantee.

## Official Status

- Official online/paper iteration: `V193`
- Historical replay source: `runs/research_v193_long_base_top5_premium6h_throttle/v193_selected_account_path.csv`
- Replay return column: `v193_account_return_pct`
- Replay PnL column: `v193_account_pnl_bps`
- Replay page target: `runs/v142_trading_replay/index.html`
- Real-money status: blocked by V204/V206 unless every safety gate passes.
- Forward monitor after the freeze currently has no new V193/V194 signal through `2026-06-15T23:59:00+00:00`.

## Input

- `runs/research_v192_long_base_low_probz_throttle/v192_selected_account_path.csv`

If the V192 selected path is missing, the V193 runner will rebuild it through the V192 runner.

## Selected Candidate Rule

- Base path: V192 selected account path.
- Target rows: `indicator_key=v125_top5_lb14_strict`, `side=long`, `leg=base`, `v188_state_action=unchanged`, `v189_state_action=unchanged`, `v190_state_action=unchanged`, `v191_state_action=unchanged`, `v192_state_action=unchanged`.
- Premium rule: `premium_close_bps_6h >= -4.576517`.
- Throttle multiplier: `0.00x` on the existing V192 account return for those rows.

V193 deliberately avoids rows already modified by V188, V189, V190, V191, or V192.

## Run

```bash
make btcusdc-v193-long-base-top5-premium6h-throttle
```

## Historical Replay

```bash
make trade-replay-v193-page
```

The legacy `trade-replay-v142-page` target is kept as an alias path for the existing static page location, but it now generates the V193 replay data.

## Focused Test

```bash
make test-btcusdc-v193
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

- `runs/research_v193_long_base_top5_premium6h_throttle/v193_policy_comparison.csv`
- `runs/research_v193_long_base_top5_premium6h_throttle/v193_selected_account_path.csv`
- `runs/research_v193_long_base_top5_premium6h_throttle/v193_selected_monthly_path.csv`
- `runs/research_v193_long_base_top5_premium6h_throttle/v193_selected_action_profile.csv`
- `runs/research_v193_long_base_top5_premium6h_throttle/v193_long_base_top5_premium6h_throttle_summary.json`
- `reports/RESEARCH_V193_BTCUSDC_LONG_BASE_TOP5_PREMIUM6H_THROTTLE.md`

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

- improve total return versus V192;
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

V193 treats insufficiently negative 6-hour premium as risk context for a remaining top5 long-base bucket. It removes size only and is not a new standalone entry or exit signal.

Forward monitoring and execution validation are still required before any live use.
