# Research V86 BTCUSDC Short-Term Recent Validation Results

## Decision

- Short-term candidate passed: `True`
- Recent edge valid: `False`
- Promote short-term candidate: `False`
- Next action: `refresh_recent_data_or_wait`

## 12h Short-Term Gate

- Trades: `184`
- Total net PnL: `4187.522330` bps
- Mean net PnL: `22.758274` bps
- Win rate: `0.538043`
- Positive fold rate: `0.857143`
- Worst fold: `-233.758850` bps
- Holdout total: `1158.060172` bps
- Holdout positive fold rate: `1.000000`
- Worst delay total: `4036.101323` bps
- Required extra cost total at +16.0 bps: `1243.522330` bps
- Failed checks: ``

## Recent Edge Gate

- Recent months: `6`
- Recent total net PnL: `622.438503` bps
- Recent calendar positive month rate: `0.500000`
- Recent active month count: `5`
- Recent active positive month rate: `0.600000`
- Tail active month count: `3`
- Tail active total net PnL: `516.127911` bps
- Tail active positive month rate: `0.333333`
- Latest active month: `2026-06`
- Latest active month net PnL: `-67.100863` bps
- Failed checks: `recent_tail_active_positive_month_rate;latest_active_month_positive`

## Time Windows

window,hours,trades,total_net_pnl_bps,mean_net_pnl_bps,win_rate,active_folds,positive_fold_rate,worst_fold_net_pnl_bps
UTC 00-04,"0,1,2,3,4",50,-454.3345151224109,-9.086690302448218,0.48,7,0.42857142857142855,-609.8774742426796
UTC 06-11,"6,7,8,9,10,11",52,1109.2026802133066,21.33082077333282,0.4807692307692308,7,0.7142857142857143,-750.4969116747436
UTC 13,13,11,198.72757802489065,18.06614345680824,0.5454545454545454,5,0.4,-478.036341452119
UTC 15,15,14,173.64576853059702,12.403269180756931,0.6428571428571429,6,0.6666666666666666,-501.2030944005668
UTC 17-19,"17,18,19",37,1675.444294811059,45.28227823813673,0.5405405405405406,7,0.7142857142857143,-92.70973782771624
UTC 21-22,"21,22",20,1484.8365235451147,74.24182617725573,0.75,7,0.5714285714285714,-199.12781120198085
V69 all kept hours,"0,1,2,3,4,6,7,8,9,10,11,13,15,17,18,19,21,22",184,4187.522330002557,22.758273532622592,0.5380434782608695,7,0.8571428571428571,-233.75885037254855

## Monthly Results

month,total_net_pnl_bps,positive
2024-01,683.4893071737549,True
2024-02,-185.72656621548012,False
2024-03,-401.38643947193464,False
2024-04,-143.72525731035768,False
2024-05,851.7519876651821,True
2024-06,4.984208638372408,True
2024-07,618.2809186747093,True
2024-08,1003.192547110378,True
2024-09,-5.6667306228222145,False
2024-10,7.602802844296661,True
2024-11,1085.140903095037,True
2024-12,-303.86471825373314,False
2025-01,297.092218840652,True
2025-02,-105.42446628899188,False
2025-03,120.59541797324795,True
2025-04,1266.0892010342375,True
2025-05,-37.2131525044515,False
2025-07,87.9143725799273,True
2025-10,-399.32902860324305,False
2025-11,-296.7341135789726,False
2025-12,-581.9795858992677,False
2026-01,63.54052299528284,True
2026-02,42.77006958294321,True
2026-03,677.737812147766,True
2026-04,-94.50903814319882,False
2026-06,-67.10086346077655,False

## Interpretation

V86 reframes V69 as a 12-hour short-term BTCUSDC research candidate instead of an all-day strategy route. Under that narrower short-term gate, the V69 candidate still passes: it has positive total PnL, positive holdout folds, positive tested delay totals, and remains positive under the +16 bps extra-cost stress.

The recent-edge gate does not pass. The last six calendar months are still net positive, but the latest active month is negative and only one of the last three active months is positive. This keeps the candidate in research/monitoring status rather than promotion status.
