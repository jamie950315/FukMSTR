# Research V47 Results

V47 tested hour-of-day transfer for the selected BTCUSDC nested-recency candidates. Hours were ranked using selector-window PnL only, then validation trades were kept only in the selected hours.

## Result

V47 did not pass the stability target.

| Best gate | Active windows | Passed windows | Validation total account return | Minimum validation account return | Median validation account return |
|---|---:|---:|---:|---:|---:|
| top 4 selector hours | 14 | 1 | -49.307691% | -29.116054% | -8.698148% |

## Interpretation

Hour-of-day gating reduces the size of the loss compared with the ungated selected-candidate replay, but it does not create stable profit. The best gate still loses money overall and passes only 1 of 14 windows.

This rules out a simple selector-window hourly gate for the current BTCUSDC nested-recency candidate path.

## Outputs

```text
runs/research_v47_btcusdc_hourly_gate/summary_v47.json
runs/research_v47_btcusdc_hourly_gate/REPORT_V47.md
runs/research_v47_btcusdc_hourly_gate/btcusdc_v47_hourly_gate_summary.csv
```
