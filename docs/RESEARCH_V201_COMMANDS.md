# V201 Realtime Signal Availability Lock Commands

V201 adds a point-in-time availability guard to the V142 paper-trading path.
It does not tune thresholds, leverage rules, entries, exits, or candidate selection.

## Focused Test

```bash
make test-btcusdc-v201
```

## Realtime-Safe Smoke Test

```bash
make paper-trade-v142-realtime-safe-smoke
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Signal CSV Fields

Required signal time:

- `timestamp`: the market time the signal refers to.

Optional point-in-time availability fields:

- `available_at`: the time the signal became available to the trading process.
- `generated_at`: accepted as an alias when `available_at` is not present.

When `available_at` or `generated_at` is present, the CSV provider waits until that time before emitting the signal.
The broker also rejects any realtime-safe signal delivered before its `available_at` time and records `future_available_at` in `rejected_signals.csv`.

This is paper-trading infrastructure only. It does not place live exchange orders and does not prove future profitability.
