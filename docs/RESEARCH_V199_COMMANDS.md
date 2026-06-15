# Research V199 Commands

V199 adds rejected-signal reason logging to the BTCUSDC paper-trading entrypoint.

It does not add trades, change signal thresholds, change trade side, or claim a new historical performance improvement. It makes realtime-safe signal rejection auditable by writing each rejected signal and its reason to disk.

This is an operational safety change, not a live trading guarantee.

## What Changed

- `PaperBroker` now records rejected realtime-safe signals in memory.
- `paper-trade-v142` now writes `rejected_signals.csv`.
- `summary.json` now includes `rejected_signals` and `rejected_signals_csv`.
- Rejection reasons include:
  - `wrong_symbol`;
  - `invalid_side`;
  - `future_signal`;
  - `stale_signal`.

## Focused Test

```bash
make test-btcusdc-v199
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Required Iteration Metrics

V199 is not a performance iteration. It keeps the V193/V194 metrics visible because those are the overfitting-risk reference points:

- account return estimate;
- improvement in percentage points;
- max drawdown;
- positive months;
- holdout return;
- holdout positive months.

