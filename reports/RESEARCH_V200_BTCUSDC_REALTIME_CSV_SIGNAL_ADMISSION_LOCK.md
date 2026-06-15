# V200 BTCUSDC Realtime CSV Signal Admission Lock

## Status

`realtime_csv_signal_admission_lock_ready`

## Review Finding

The V199 rejection log exposed a remaining realtime audit gap:

- `CsvSignalProvider` silently skipped rows whose `symbol` did not match the snapshot symbol.
- `CsvSignalProvider` silently dropped `side = 0`.
- `CsvSignalProvider` clipped abnormal side values into the `-1..1` range.

That meant a malformed realtime CSV signal could disappear without appearing in `rejected_signals.csv`, or worse, a value such as `side = 2` or `side = 1.5` could be converted into a long signal.

## V200 Change

V200 moves admission responsibility to the broker layer:

- `CsvSignalProvider` emits ready CSV rows once, without silently filtering wrong-symbol rows.
- Side values are preserved numerically instead of clipped.
- `PaperBroker` admits only exact `-1` or `1` side values.
- `realtime_safe` logs wrong-symbol and invalid-side rows with explicit reasons.
- `research_v142` keeps historical stale replay for valid rows, while ignoring invalid or wrong-symbol rows.

## Performance Metrics

V200 does not tune thresholds, leverage, entries, exits, or candidate selection. The latest promoted research-candidate metrics remain:

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
