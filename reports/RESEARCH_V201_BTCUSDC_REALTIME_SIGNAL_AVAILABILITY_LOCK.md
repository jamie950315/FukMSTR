# V201 BTCUSDC Realtime Signal Availability Lock

## Status

`realtime_signal_availability_lock_ready`

## Review Finding

V200 made malformed CSV signal rows auditable, but the realtime path still had one point-in-time gap:

- `timestamp` described the market time of the signal.
- There was no separate field proving when the signal was actually generated or became available.

That matters because a historical CSV can contain a signal row with a past `timestamp` even if the signal was created later. Without an availability timestamp, replay can accidentally act as if a late-generated signal was known earlier.

## V201 Change

V201 adds an optional signal availability timestamp:

- `PaperSignal.available_at`
- CSV `available_at`
- CSV `generated_at` alias

The CSV provider now waits until the availability time before emitting a row.
The broker also rejects any realtime-safe signal delivered before its availability time with reason `future_available_at`.
Rejected signal logs now include the `available_at` field.

## Performance Metrics

V201 does not tune strategy logic. The latest promoted research-candidate metrics remain:

| Metric | V193 | V194 |
|---|---:|---:|
| Estimated account return | +3950.66% | +4044.70% |
| Improvement | - | +94.04 percentage points |
| Max drawdown | -30.20% | -30.20% |
| Positive months | 24/24 | 24/24 |
| Holdout return | +1386.21% | +1452.80% |
| Holdout months | 6/6 | 6/6 |

## Validation Commands

```bash
make test-btcusdc-v201
make test-btcusdc-v200
make test-btcusdc-v199
make test-btcusdc-v198
make test-btcusdc-v197
make paper-trade-v142-realtime-safe-smoke
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Caveat

This remains research and paper-trading infrastructure. Forward monitoring and execution validation are still required before any live use.
