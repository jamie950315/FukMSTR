# Research V198 Commands

V198 is a realtime stale-signal lock for the BTCUSDC paper-trading entrypoint.

It does not add trades, change signal thresholds, change trade side, or claim a new historical performance improvement. It prevents realtime-safe paper trading from opening positions on old or future signals.

This is an operational safety change, not a live trading guarantee.

## What Changed

- `PaperTradingConfig` now includes `max_realtime_signal_age_minutes`, defaulting to `5.0`.
- `realtime_safe` accepts only signals that:
  - match the current snapshot symbol;
  - have side `1` or `-1`;
  - are not future-dated;
  - are no older than the configured signal-age limit.
- `research_v142` keeps historical replay behavior, so old historical signals can still be replayed intentionally.
- Snapshot events now record `rejected_signal_count`.

## Focused Test

```bash
make test-btcusdc-v198
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Required Iteration Metrics

V198 is not a performance iteration. It keeps the V193/V194 metrics visible because those are the overfitting-risk reference points:

- account return estimate;
- improvement in percentage points;
- max drawdown;
- positive months;
- holdout return;
- holdout positive months.

