# Research V41 Results

V41 tested whether 5-second aggTrade bars improve BTCUSDC validation on the V32 independent split.

## Result

V41 did not pass the target.

| Metric | Value |
|---|---:|
| Bars | 317579 |
| Candidate count | 2100 |
| Selected validation account return | -196.647653% |
| Oracle validation account return | 9.415268% |
| Top-K best validation account return | -104.837303% |
| Target | 50.000000% |

## Interpretation

The shorter 5-second aggregation does not solve the problem. Unlike the 1-minute aggTrade-flow YTD run, this independent 5-second split does not even contain an oracle candidate that reaches +50%.

This rules out the simple explanation that the earlier failure was caused only by 1-minute aggregation being too coarse.

## Outputs

```text
runs/research_v41_btcusdc_aggtrade_5s_probe/summary_v41.json
runs/research_v41_btcusdc_aggtrade_5s_probe/REPORT_V41.md
```
