# V203 BTCUSDC Market Data Price Validity Lock

## Status

`market_data_price_validity_lock_ready`

## Review Finding

The V142 paper-trading broker trusted every incoming market snapshot price.

That created a realtime safety issue:

- `price = 0` could open a position with entry price zero.
- Later equity calculation could divide by zero.
- Invalid prices could also be used for final equity estimation.

## V203 Change

V203 adds a market data validity lock:

- invalid prices are logged as `market_data_error`,
- invalid prices do not consume signals in the runner,
- invalid prices do not open or close positions,
- invalid prices are not used for final equity estimation,
- `summary.json` now includes `market_data_errors`.

## Iteration Metrics

| Metric | V203 |
|---|---:|
| Strategy thresholds changed | No |
| Entry/exit logic changed | No |
| Leverage logic changed | No |
| New backtest return improvement claimed | No |
| New realtime safety check | Yes |
| New market data error count | Yes |

## Validation Commands

```bash
make test-btcusdc-v203
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
