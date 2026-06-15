# V202 Rejected Signal Reason Summary Commands

V202 improves realtime monitoring for the V142 paper-trading path.
It does not tune thresholds, leverage rules, entries, exits, or candidate selection.

## Focused Test

```bash
make test-btcusdc-v202
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

## What V202 Adds

The paper-trading summary now includes:

```json
"rejected_signal_reasons": {
  "invalid_side": 1,
  "stale_signal": 1,
  "wrong_symbol": 1
}
```

The dashboard also includes a `Rejected Signal Reasons` section.

This makes realtime paper monitoring easier to diagnose:

- `wrong_symbol`: symbol mismatch.
- `invalid_side`: malformed signal direction.
- `future_signal`: signal timestamp is ahead of the market snapshot.
- `future_available_at`: signal was delivered before it was available.
- `stale_signal`: signal is older than the realtime-safe age limit.

This is paper-trading infrastructure only. It does not place live exchange orders and does not prove future profitability.
