# Research V44 Results

V44 tested prequential candidate-level meta-selection on V43 nested recency candidate evaluations. The model trained only on completed folds and selected one candidate for the next fold.

## Result

V44 did not pass the stability target.

| Best run | Active windows | Passed windows | Total validation account return | Minimum validation account return | Median validation account return |
|---|---:|---:|---:|---:|---:|
| random_forest_warmup2 | 12 | 2 | 132.263838% | -42.932380% | 8.370483% |

## Interpretation

The candidate-level meta-selector improves total validation return versus V43's direct nested recency selector, but it is still not stable. Only 2 of 12 active windows pass the 50% target, and the worst active window remains negative.

This suggests that the V43 candidate features contain some weak signal, but not enough to reliably identify the >50% candidates that the oracle audit shows exist in every fold.

## Outputs

```text
runs/research_v44_btcusdc_prequential_meta_selector/summary_v44.json
runs/research_v44_btcusdc_prequential_meta_selector/REPORT_V44.md
runs/research_v44_btcusdc_prequential_meta_selector/btcusdc_v44_summary.csv
runs/research_v44_btcusdc_prequential_meta_selector/btcusdc_v44_random_forest_warmup2_folds.csv
```
