# V200 Realtime CSV Signal Admission Lock Commands

V200 is a realtime-safety and auditability change for the V142 paper-trading tool.
It does not tune trading thresholds, leverage rules, or candidate selection.

## Focused Test

```bash
make test-btcusdc-v200
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

## What V200 Locks

- CSV signal rows are no longer silently dropped by symbol before broker admission.
- CSV signal side values are no longer clipped into the `-1..1` range.
- Realtime-safe mode admits only exact `side = -1` or `side = 1`.
- Realtime-safe mode logs rejected CSV rows to `rejected_signals.csv`.
- Research mode still permits historical stale replay, but it does not open invalid or wrong-symbol CSV signals.

This is paper-trading infrastructure only. It does not place live exchange orders and does not prove future profitability.
