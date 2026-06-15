# V202 BTCUSDC Rejected Signal Reason Summary

## Status

`rejected_signal_reason_summary_ready`

## Review Finding

V199 added `rejected_signals.csv`, V200 made invalid CSV rows auditable, and V201 added point-in-time availability checks.

The remaining monitoring gap was that `summary.json` only reported the total rejected signal count. During realtime monitoring, that is not enough to distinguish:

- no usable signals,
- stale signals,
- malformed side values,
- wrong symbols,
- future signal timestamps,
- signals delivered before `available_at`.

## V202 Change

V202 adds `rejected_signal_reasons` to the paper-trading summary and dashboard.

Example:

```json
{
  "rejected_signals": 3,
  "rejected_signal_reasons": {
    "invalid_side": 1,
    "stale_signal": 1,
    "wrong_symbol": 1
  }
}
```

The dashboard now includes a `Rejected Signal Reasons` section.

## Performance Metrics

V202 does not tune strategy logic. The latest promoted research-candidate metrics remain:

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
make test-btcusdc-v202
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
