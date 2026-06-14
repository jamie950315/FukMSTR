# Research V45 Results

V45 added path-shape metrics to BTCUSDC candidate evaluations, reran nested recency, and tested prequential candidate-level meta-selection with the enhanced feature set.

## Result

V45 did not pass the stability target.

| Best run | Active windows | Passed windows | Total validation account return | Minimum validation account return | Median validation account return |
|---|---:|---:|---:|---:|---:|
| random_forest_warmup6 | 8 | 1 | 121.306190% | -17.447317% | 11.342110% |

## Interpretation

The added path-shape metrics do not solve the selection problem. They reduce the best run's worst active window compared with V44, but the pass count falls to 1 active window and the active windows still do not reliably reach 50%.

This rules out the current enhanced aggregate-metric feature set as a stable selector for the BTCUSDC aggTrade-flow candidate family.

## Outputs

```text
runs/research_v45_btcusdc_enhanced_nested_recency/summary_v43.json
runs/research_v45_btcusdc_enhanced_nested_recency/btcusdc_v43_candidate_evaluations.csv
runs/research_v45_btcusdc_enhanced_meta_selector/summary_v45.json
runs/research_v45_btcusdc_enhanced_meta_selector/REPORT_V45.md
runs/research_v45_btcusdc_enhanced_meta_selector/btcusdc_v45_summary.csv
```
