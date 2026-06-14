# Research V40 Results

V40 audited whether equal-weight top-K candidate portfolios can reduce selector error. Each fold selects top-K candidates by calibration-only score, then evaluates the average validation account return.

## Result

V40 did not pass the stability target.

| Source | Best calibration score | Best K | Passed windows | Total validation account return | Minimum validation account return |
|---|---|---:|---:|---:|---:|
| aggtrade_flow_ytd | calibration_account_return_pct | 2 | 1/14 | -319.573878% | -86.689562% |
| kline_ytd_broad | calibration_min_day_net_pnl_bps | 1 | 2/14 | 228.203479% | -23.799113% |

## Interpretation

Top-K averaging does not solve the BTCUSDC selector problem. The aggTrade-flow candidate set remains negative. The older kline candidate set has a positive total under one calibration-min-day selector, but only 2 of 14 windows reach +50%, so it is not stable.

This rules out a simple diversification fix at the candidate-evaluation level.

## Outputs

```text
runs/research_v40_btcusdc_topk_portfolio/summary_v40.json
runs/research_v40_btcusdc_topk_portfolio/REPORT_V40.md
runs/research_v40_btcusdc_topk_portfolio/btcusdc_v40_aggtrade_flow_ytd_summary.csv
runs/research_v40_btcusdc_topk_portfolio/btcusdc_v40_kline_ytd_broad_summary.csv
```
