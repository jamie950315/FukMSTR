# Research V46 Results

V46 tested fixed candidate-family transfer. Each run selected a family using folds 1-7 only, then evaluated the same family on held-out folds 8-14.

## Result

V46 did not pass the stability target.

| Best run | Validation windows | Passed windows | Validation total account return | Minimum validation account return | Median validation account return |
|---|---:|---:|---:|---:|---:|
| horizon_direction_feature_quantile_selector_day_positive_rate | 7 | 1 | -72.284250% | -81.522490% | -24.515944% |

## Interpretation

Fixed family transfer does not hold. Families that look strongest in folds 1-7 do not remain profitable in folds 8-14. The best held-out run still loses money and only passes 1 of 7 validation windows.

This rules out a simple fixed-family lock as a stable BTCUSDC solution for the current aggTrade-flow candidate grid.

## Outputs

```text
runs/research_v46_btcusdc_fixed_family_transfer/summary_v46.json
runs/research_v46_btcusdc_fixed_family_transfer/REPORT_V46.md
runs/research_v46_btcusdc_fixed_family_transfer/btcusdc_v46_summary.csv
```
