# Research V196 Commands

V196 is a BTCUSDC forward monitoring gate for the post-overfitting-audit state.

It does not add trades, change trade side, change thresholds, or promote live trading. It freezes historical optimization and checks whether enough rows exist after the freeze timestamp to make any forward-validation claim.

This is a research monitoring gate, not a live trading guarantee.

## Input

- `runs/research_v194_long_rescue_premium_discount_stepup/v194_selected_account_path.csv`

If the V194 selected path is missing, the V196 runner will rebuild it through the V194 runner.

## Freeze Timestamp

- `2026-06-09T16:40:00Z`

Rows at or before this timestamp are historical and cannot validate V194.

## Run

```bash
make btcusdc-v196-forward-monitoring-gate
```

## Focused Test

```bash
make test-btcusdc-v196
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

- `runs/research_v196_forward_monitoring_gate/v196_version_metrics.csv`
- `runs/research_v196_forward_monitoring_gate/v196_forward_monitoring_table.csv`
- `runs/research_v196_forward_monitoring_gate/v196_forward_monitoring_gate_summary.json`
- `reports/RESEARCH_V196_BTCUSDC_FORWARD_MONITORING_GATE.md`

The `runs/` outputs are local generated artifacts and should not be committed.

## Required Iteration Metrics

The report keeps the required V193 vs V194 metrics:

- account return estimate;
- improvement in percentage points;
- max drawdown;
- positive months;
- holdout return;
- holdout positive months.

## Interpretation

V196 enforces the V195 conclusion: historical optimization is frozen. V194 remains an aggressive research candidate, V193 remains the conservative comparison, and forward evidence requires new post-freeze rows.
