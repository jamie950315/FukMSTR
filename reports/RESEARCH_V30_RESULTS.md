# Research V30 Results

V30 measures whether the broad public 1m candle candidate set contains profitable validation candidates, and whether the current calibration-return selector can find them.

## Aggregate

| Metric | Value |
|---|---:|
| Folds | 14 |
| Oracle windows passed | 13 |
| Oracle windows failed | 1 |
| Calibration selector windows passed | 0 |
| Calibration selector windows failed | 14 |
| Pass gap | 13 |
| Oracle total validation account return | 1472.2869% |
| Selector total validation account return | -339.0036% |

## Interpretation

The candidate set has strong validation winners in almost every fold, but the current selector cannot identify them using calibration return. The issue is not only weak execution or fees; it is candidate selection.

The next research step should be a meta-selector that predicts candidate family from market regime features, rather than choosing the candidate with the best calibration PnL.

## Caveat

Oracle performance is not tradable because it uses validation outcomes. V30 is a failure diagnosis, not a trading certificate.
