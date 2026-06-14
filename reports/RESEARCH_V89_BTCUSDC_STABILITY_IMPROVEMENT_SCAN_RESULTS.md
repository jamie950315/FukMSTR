# Research V89 BTCUSDC Stability Improvement Scan Results

## Decision

- Promote stability repair: `True`
- Mechanical selected policy: `remove_hours_0_2_3_4`
- Mechanical selected total improvement: `1465.026418` bps
- Mechanical selected drawdown improvement: `39.962065` bps
- Conservative same-family policy: `stricter_oversold_short_veto_-550`

## Baseline V88

- Trades: `127`
- Total net PnL: `3660.879838` bps
- Mean net PnL: `28.825825` bps
- Win rate: `0.566929`
- Max drawdown: `1581.729864` bps

## Mechanical Selected Policy

- Policy: `remove_hours_0_2_3_4`
- Description: Remove UTC hours 0, 2, 3, and 4 from the V87 two-year ledger.
- Trades: `102`
- Total net PnL: `5125.906257` bps
- Mean net PnL: `50.253983` bps
- Win rate: `0.607843`
- Max drawdown: `1541.767799` bps
- Active positive month rate: `0.650000`
- Rolling 3m positive rate: `0.782609`
- Rolling 6m positive rate: `0.750000`

## Conservative Same-Family Policy

- Policy: `stricter_oversold_short_veto_-550`
- Description: Tighten the V87 oversold-short veto from -650 bps to -550 bps.
- Trades: `112`
- Total net PnL: `4534.913160` bps
- Mean net PnL: `40.490296` bps
- Win rate: `0.607143`
- Max drawdown: `1408.234060` bps
- Active positive month rate: `0.666667`
- Rolling 3m positive rate: `0.782609`
- Rolling 6m positive rate: `0.750000`

## Candidate Scan

policy,family,stable_enough,failed_checks,trade_count,total_net_pnl_bps,mean_net_pnl_bps,win_rate,max_drawdown_bps,required_extra_cost_total_net_pnl_bps,worst_delay_total_net_pnl_bps,active_positive_month_rate,calendar_positive_month_rate,positive_quarter_rate,rolling_3m_positive_rate,rolling_6m_positive_rate,rolling_12m_positive_rate,rolling_3m_worst_net_pnl_bps,rolling_6m_worst_net_pnl_bps
remove_hours_0_2_3_4,hour_gate,True,,102,5125.906256516064,50.25398290702024,0.6078431372549019,1541.767798958419,3493.906256516065,4616.9141625548045,0.65,0.52,0.7777777777777778,0.782608695652174,0.75,1.0,-729.714875137055,-641.8005025571276
remove_hours_0_3_4_6,hour_gate,True,,103,4922.685985523018,47.793067820611824,0.6213592233009708,1541.767798958419,3274.6859855230186,4548.802296886695,0.7,0.56,0.7777777777777778,0.782608695652174,0.75,1.0,-729.714875137055,-641.8005025571274
remove_hours_0_3_4_7,hour_gate,True,,104,4687.61616734231,45.07323237829144,0.5961538461538461,1291.368815293606,3023.6161673423103,4231.452565748394,0.65,0.52,0.7777777777777778,0.782608695652174,0.75,1.0,-729.714875137055,-641.8005025571276
stricter_oversold_short_veto_-550,same_veto,True,,112,4534.913159647622,40.49029606828234,0.6071428571428571,1408.2340595779942,2742.913159647622,4121.343214059284,0.6666666666666666,0.56,0.7777777777777778,0.782608695652174,0.75,1.0,-930.8951771343568,-842.9808045544296
remove_hours_3_4_7_11,hour_gate,True,,105,4292.176668053769,40.87787302908352,0.5904761904761905,1291.368815293606,2612.17666805377,3760.1369756831787,0.6842105263157895,0.52,0.7777777777777778,0.782608695652174,0.75,1.0,-681.5557083722211,-593.6413357922936
remove_hours_0_2_3_plus_no_high_volume_negative_flow,hybrid,False,min_trades,89,5201.550919751673,58.444392356760375,0.6404494382022472,1420.4154087449988,3777.550919751673,4506.260850996322,0.6,0.48,0.7777777777777778,0.8260869565217391,0.85,1.0,-195.67092637006203,-279.0690734670965
stricter_oversold_short_veto_-500,same_veto,False,active_month_positive_rate;rolling_3m_positive_rate,104,4896.479529683523,47.081533939264645,0.625,805.6184767122672,3232.4795296835227,4390.304496956825,0.5714285714285714,0.48,0.7777777777777778,0.7391304347826086,0.8,1.0,-618.9113341302995,-702.3094812273339
stricter_oversold_short_veto_-600,same_veto,False,active_month_positive_rate;rolling_3m_positive_rate;rolling_6m_positive_rate,119,4453.091420221146,37.42093630437938,0.5882352941176471,1408.2340595779947,2549.0914202211475,4394.899982207494,0.5714285714285714,0.48,0.7777777777777778,0.7391304347826086,0.7,0.7857142857142857,-930.8951771343568,-842.9808045544296
no_high_volume_negative_flow,regime_filter,False,active_month_positive_rate,105,4147.184041182878,39.49699086840836,0.6095238095238096,1420.4154087449988,2467.184041182878,3551.207630392289,0.5,0.4,0.7777777777777778,0.782608695652174,0.75,1.0,-546.9943050153745,-716.7108919029121

## Mechanical Selected Months

month,trades,total_net_pnl_bps,positive
2024-06,0,0.0,False
2024-07,7,786.682379675572,True
2024-08,14,1210.905177493105,True
2024-09,5,-5.6667306228222145,False
2024-10,1,7.602802844296661,True
2024-11,6,789.2204703157478,True
2024-12,5,166.32390568975896,True
2025-01,10,515.950625174882,True
2025-02,10,-105.42446628899188,False
2025-03,6,-260.1856354208277,False
2025-04,12,1690.4168606646363,True
2025-05,1,-37.2131525044515,False
2025-06,0,0.0,False
2025-07,2,87.9143725799273,True
2025-08,0,0.0,False
2025-09,0,0.0,False
2025-10,3,-399.32902860324305,False
2025-11,4,54.95600901816512,True
2025-12,1,-385.341855551977,False
2026-01,2,168.8379766905571,True
2026-02,7,207.21815620778028,True
2026-03,4,552.1818371294626,True
2026-04,1,-94.50903814319882,False
2026-05,0,0.0,False
2026-06,1,175.36559016768555,True

## Conservative Same-Family Months

month,trades,total_net_pnl_bps,positive
2024-06,1,4.984208638372408,True
2024-07,9,719.6376346222672,True
2024-08,13,339.6010171599151,True
2024-09,4,122.09194681583615,True
2024-10,1,7.602802844296661,True
2024-11,8,1012.3147810369152,True
2024-12,6,-68.78684794086826,False
2025-01,9,288.2428607708182,True
2025-02,9,-93.2431171219879,False
2025-03,10,-49.59876470942032,False
2025-04,12,1690.4168606646363,True
2025-05,1,-37.2131525044515,False
2025-06,0,0.0,False
2025-07,2,87.9143725799273,True
2025-08,0,0.0,False
2025-09,0,0.0,False
2025-10,3,-399.32902860324305,False
2025-11,5,50.41343736815391,True
2025-12,3,-581.9795858992677,False
2026-01,2,168.8379766905571,True
2026-02,6,596.5290321276594,True
2026-03,5,677.737812147766,True
2026-04,1,-94.50903814319882,False
2026-05,0,0.0,False
2026-06,2,93.24795110293861,True

## Interpretation

V89 shows the V88 instability is repairable inside the current two-year BTCUSDC evidence. The mechanical best passing candidate removes UTC 0, 2, 3, and 4; it raises total PnL and passes all V88 stability checks with 102 trades.

The cleaner same-family repair tightens the existing V87 oversold-short veto from -650 bps to -550 bps. It also passes all V88 stability checks with 112 trades, lower drawdown than V88, positive delay stress, and positive +16 bps cost stress.

Both are research candidates selected after looking at the two-year instability. They are not live-trading guarantees and need fresh forward monitoring before being treated as production-ready.
