# Research V31 Results

V31 tested whether simple BTCUSDC selector policies can repair the V29/YTD rolling failure without looking at the current validation fold.

## Result

V31 did not pass the stability target.

| Metric | Value |
|---|---:|
| Folds | 14 |
| Warmup folds | 2 |
| Active validation windows | 12 |
| Risk-off windows | 2 |
| Passed windows at +50% account return | 1 |
| Failed active windows | 11 |
| Total validation account return | -215.674247% |
| Minimum validation account return | -78.362384% |
| Median validation account return | -16.598785% |
| Best static policy passed windows | 3 |
| Best static policy total validation account return | 26.204325% |

## Interpretation

The broad candidate set still contains profitable validation candidates, but simple calibration-only selector policies do not identify them reliably out of sample. The strongest static policy in V31 was `calibration_win_rate` over `momentum` candidates with `quantile_max=0.9`, yet it only passed 3 of 14 folds and did not clear the total or per-window target.

The prequential selector, which chooses each fold's policy from prior completed folds only, passed only 1 of 12 active windows. This confirms the main failure is selector instability, not merely a missing sort key.

## Outputs

```text
runs/research_v31_btcusdc_prequential_selector/REPORT_V31.md
runs/research_v31_btcusdc_prequential_selector/summary_v31.json
runs/research_v31_btcusdc_prequential_selector/btcusdc_v31_prequential_folds.csv
runs/research_v31_btcusdc_prequential_selector/btcusdc_v31_static_policy_summary.csv
```
