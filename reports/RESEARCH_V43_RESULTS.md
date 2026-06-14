# Research V43 Results

V43 tested nested recency selection on BTCUSDC aggTrade 1m flow bars. The selector used only the later half of each calibration window, and the selected candidate was then applied to the next forward validation window.

## Result

V43 did not pass the stability target.

| Metric | Value |
|---|---:|
| Folds | 14 |
| Active validation windows | 14 |
| Risk-off windows | 0 |
| Windows >= 50% target | 0 |
| Total validation trades | 717 |
| Total validation account return | -489.393090% |
| Minimum validation account return | -103.866382% |
| Median validation account return | -35.872331% |

## Interpretation

Nested recency selection does not transfer to the next BTCUSDC validation window. The selector slice often shows strong positive returns, but the following validation slice reverses sharply. This rules out a simple "recent winner continues" selector for the current BTCUSDC aggTrade-flow candidate family.

The important result is negative: V43 reduces validation leakage, but it still produces 0/14 passing windows and a large negative total return.

## Outputs

```text
runs/research_v43_btcusdc_nested_recency/summary_v43.json
runs/research_v43_btcusdc_nested_recency/REPORT_V43.md
runs/research_v43_btcusdc_nested_recency/btcusdc_v43_fold_metrics.csv
runs/research_v43_btcusdc_nested_recency/btcusdc_v43_candidate_evaluations.csv
runs/research_v43_btcusdc_nested_recency/btcusdc_v43_validation_trades.csv
```
