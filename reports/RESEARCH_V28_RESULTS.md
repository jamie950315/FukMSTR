# Research V28 Results

V28 extends BTCUSDC validation from one held-out window to rolling forward windows.

## Setup

| Item | Value |
|---|---:|
| Data | BTCUSDC Binance USD-M public 1m klines |
| Dates | 2026-03-13 through 2026-06-10 |
| Downloaded files | 90 |
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
| Rolling folds | 7 |
| Risk-off windows | 6 |
| Active validation windows | 1 |
| Active windows passed | 1 |
| Active windows failed | 0 |
| Active validation target passed | true |
| All calendar windows target passed | false |
| Total active validation trades | 53 |
| Total active validation account return | 97.7852% |
| Minimum calendar-window account return | 0.0% |

## Interpretation

The risk gate prevents trading in weak calibration regimes. On the only active forward window, the selected rule exceeds the 50% target.

This is a stronger result than V27, but it still does not prove that every 10-day period can earn more than 50%. Most windows are risk-off, so the result should be read as: the system can avoid weak regimes and exceed 50% when the calibration gate activates.

## Caveat

The validation uses public 1m candles, not L2 order-book data. It does not guarantee future profitability.
