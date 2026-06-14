# Research V27 Results

V27 tests a BTCUSDC-only public 1m kline rule with a strict date split.

## Split

| Split | Dates |
|---|---|
| Calibration | 2026-05-22 through 2026-05-31 |
| Validation | 2026-06-01 through 2026-06-10 |

## Selected Candidate

The candidate was selected only from calibration metrics.

| Field | Value |
|---|---:|
| Direction | short |
| Lookback | 2 minutes |
| Horizon | 240 minutes |
| Filter | volume ratio |
| Calibration quantile | 0.98 |
| Threshold | 1.8319559464902484 |
| Fee | 8.5 bps per round trip |
| Leverage | 8x |

## Result

| Metric | Calibration | Validation |
|---|---:|---:|
| Trades | 47 | 23 |
| Total net PnL | 142.1344 bps | 879.7752 bps |
| Account return at 8x | 11.3708% | 70.3820% |
| Win rate | 40.4255% | 65.2174% |
| Positive day rate | 60.0% | 70.0% |

The validation account return exceeds the 50% target on the available held-out dates.

## Caveat

This result is not a production proof. It uses Binance public 1m candles, not L2 order-book data, and validates on 10 held-out days. Further work should extend the date range and replay execution with order-book or trade-level data before treating it as stable.
