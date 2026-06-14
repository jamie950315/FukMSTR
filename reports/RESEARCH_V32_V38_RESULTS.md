# Research V32-V38 Results

V32-V38 tested BTCUSDC public `aggTrades` aggregated into 1-minute taker-flow bars. The goal was to check whether richer trade-flow data can produce stable validation profit without selecting from the validation period.

## Results

| Run | Scope | Result |
|---|---|---:|
| V32 | 20-day independent split | validation account return `-38.757023%` |
| V33 | 90-day rolling, 7 folds | 0/7 windows passed, total `-391.040267%` |
| V36 | YTD rolling, 14 folds | 0/14 windows passed, total `-456.286815%` |
| V37 | YTD oracle gap | oracle passed 14/14, oracle total `+1860.850390%` |
| V38 | YTD prequential selector | 0/12 active windows passed, total `-901.443828%` |

## Interpretation

The richer aggTrade flow candidate set contains many profitable validation candidates in hindsight. V37 shows that the oracle can pass all 14 YTD validation windows.

That is not deployable. The strict calibration-only and prequential selectors fail badly. V38 confirms that simple selector policies cannot choose the winners using only prior completed folds.

The current blocker is candidate selection, not a lack of profitable hindsight candidates.

## Outputs

```text
runs/research_v32_btcusdc_aggtrade_flow/summary_v27.json
runs/research_v33_btcusdc_aggtrade_flow_rolling/summary_v28.json
runs/research_v36_btcusdc_aggtrade_flow_ytd_rolling/summary_v28.json
runs/research_v37_btcusdc_aggtrade_flow_ytd_oracle_gap/summary_v37.json
runs/research_v38_btcusdc_aggtrade_flow_ytd_prequential_selector/summary_v38.json
```
