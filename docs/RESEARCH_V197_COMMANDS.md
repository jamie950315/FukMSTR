# Research V197 Commands

V197 is a realtime overfit lock for the BTCUSDC paper-trading entrypoint.

It does not add trades, change signal thresholds, change trade side, or claim a new historical performance improvement. It changes the realtime paper-trading default from the historical V142 leverage policy to a conservative realtime-safe policy.

This is an operational safety change, not a live trading guarantee.

## What Changed

- `paper-trade-v142` now defaults to `--strategy-mode realtime_safe`.
- `realtime_safe` caps paper-trading leverage at `1.0x` and disables the historical high-confidence rescue `5x` path.
- The old V142 historical behavior is still available only when explicitly requested with `--strategy-mode research_v142`.
- The generated `paper_config.json` records the selected `strategy_mode`.

## Safe Realtime Smoke Run

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli paper-trade-v142 \
  --out runs/paper_v142_realtime_safe_smoke \
  --source synthetic \
  --ticks 3 \
  --interval-sec 60 \
  --clean \
  --no-sleep
```

## Historical Research Replay Mode

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli paper-trade-v142 \
  --out runs/paper_v142_research_mode_smoke \
  --source synthetic \
  --strategy-mode research_v142 \
  --ticks 3 \
  --interval-sec 60 \
  --clean \
  --no-sleep
```

## Focused Test

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q \
  tests/test_paper_trading_v142.py \
  tests/test_btcusdc_v195_post_goal_overfitting_audit.py \
  tests/test_btcusdc_v196_forward_monitoring_gate.py
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Required Iteration Metrics

V197 is not a performance iteration. It keeps the V193/V194 metrics visible because those are the overfitting-risk reference points:

- account return estimate;
- improvement in percentage points;
- max drawdown;
- positive months;
- holdout return;
- holdout positive months.

