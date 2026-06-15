# V203 Market Data Price Validity Lock Commands

V203 improves realtime safety for the V142 paper-trading path.
It does not tune thresholds, leverage rules, entries, exits, or candidate selection.

## Focused Test

```bash
make test-btcusdc-v203
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

## What V203 Adds

V203 rejects invalid market prices before they can affect paper-trading positions:

- `price <= 0`
- non-finite prices such as `inf`
- non-numeric price values that reach the broker layer

Invalid market snapshots are logged as `market_data_error` events.
They do not open new positions, do not close existing positions, and are not used for final equity estimation.

The paper-trading summary now includes:

```json
"market_data_errors": 1
```

This is paper-trading infrastructure only. It does not place live exchange orders and does not prove future profitability.
