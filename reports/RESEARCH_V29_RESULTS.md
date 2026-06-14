# Research V29 Results

V29 extends the V28 risk-gated BTCUSDC rolling validation to 2026 year-to-date data.

## Setup

| Item | Value |
|---|---:|
| Data | BTCUSDC Binance USD-M public 1m klines |
| Dates | 2026-01-01 through 2026-06-10 |
| Downloaded files | 161 |
| Calibration window | 20 days |
| Validation window | 10 days |
| Step | 10 days |
| Leverage | 8x |
| Round-trip fee | 8.5 bps |
| Target | 50% account return |
| Risk gate | calibration account return >= 25% |

## Aggregate

| Metric | Value |
|---|---:|
| Rolling folds | 14 |
| Risk-off windows | 9 |
| Active validation windows | 5 |
| Active windows passed | 0 |
| Active windows failed | 5 |
| All active windows target passed | false |
| All calendar windows target passed | false |
| Total active validation trades | 213 |
| Total active validation account return | -82.0959% |
| Minimum active validation window | -49.0039% |

## Interpretation

V29 fails the stability goal. The V28 risk gate avoids many weak regimes, but when tested from 2026-01-01 through 2026-06-10 it still activates in five windows and all five active windows fail the 50% target.

The V27 and V28 successes are therefore not enough to claim stable profitability. The current public 1m candle method needs a stronger regime filter, a different signal family, or true L2/trade-level replay before the full goal can be marked complete.

## Caveat

This validation uses public 1m candles, not L2 order-book data. It is a failure audit, not a production trading certificate.
