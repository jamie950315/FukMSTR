# Research V42 Results

V42 tested fixed quantile-band selectors. The idea was to avoid the most overfit calibration winners by selecting candidates from a calibration percentile band.

## Result

V42 did not pass the stability target.

| Source | Best band | Best score | Passed windows | Total validation account return | Minimum validation account return |
|---|---|---|---:|---:|---:|
| aggtrade_flow_ytd | calibration_trades 30%-50% | calibration_account_return_pct desc | 2/14 | 153.724496% | -69.925826% |
| kline_ytd_broad | calibration_min_day_net_pnl_bps 0%-20% | calibration_win_rate desc | 4/14 | 17.642838% | -94.228551% |

## Interpretation

Avoiding the top calibration candidates is not enough. The best kline run improves the number of passed windows to 4/14, but total return is near flat and the worst fold remains deeply negative. The aggTrade-flow run has positive total return but only 2/14 windows pass and the worst fold is also negative.

This rules out a simple fixed percentile-band selector as a stable solution.

## Outputs

```text
runs/research_v42_btcusdc_quantile_band_selector/summary_v42.json
runs/research_v42_btcusdc_quantile_band_selector/REPORT_V42.md
runs/research_v42_btcusdc_quantile_band_selector/btcusdc_v42_aggtrade_flow_ytd_summary.csv
runs/research_v42_btcusdc_quantile_band_selector/btcusdc_v42_kline_ytd_broad_summary.csv
```
