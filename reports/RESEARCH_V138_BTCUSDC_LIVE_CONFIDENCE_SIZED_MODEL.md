# Research V138 BTCUSDC Live Confidence Sized Model

## Decision

- V137 total PnL: `43365.441686` bps
- V137 win rate: `0.606202`
- V137 max drawdown: `1600.298249` bps
- V137 worst month: `2025-09` `2.340057` bps
- V138 total PnL: `45046.474101` bps
- V138 vs V137: `1.038764`
- V138 win rate: `0.606202`
- V138 max drawdown: `1600.298249` bps
- Trade count: `645`
- Skipped by drawdown guard: `18`
- Positive months: `24/24`
- Worst month: `2025-09` `2.340057` bps
- V138 model-improvement gate passed: `True`
- Status: `confidence_sized_model_improvement_candidate_found`

## Monthly PnL

month,weighted_net_pnl_bps
2024-07,201.9912533591219
2024-08,434.1315462601444
2024-09,3.043246512906819
2024-10,73.0023076550124
2024-11,2347.6811917843443
2024-12,7248.45955299087
2025-01,1842.625236229945
2025-02,1914.4286057582478
2025-03,1980.7579108754398
2025-04,103.48136347885671
2025-05,353.77813898407675
2025-06,46.31386995552499
2025-07,164.42841488934843
2025-08,15.941086909943627
2025-09,2.340056510835918
2025-10,10076.175768614412
2025-11,3157.468983994205
2025-12,581.3426190459079
2026-01,144.583972143911
2026-02,8027.496195305787
2026-03,1357.803753491389
2026-04,425.14758775009705
2026-05,4.353089002897933
2026-06,4539.698349836697

## Source Summary

leg,source,trade_count,total_net_pnl_bps,win_rate
base,v122_drought,84,25719.627002921945,0.6785714285714286
rescue,v138_confidence_sized_weighted_family_rescue,95,14981.517445024301,0.6947368421052632
base,v123_threshold,45,1855.362913406113,0.6888888888888889
base,v120_peak,114,1311.6431134932782,0.5614035087719298
base,v125_top7_lb14_coverage,246,1034.0098083517341,0.5650406504065041
base,v125_top5_lb14_strict,51,157.85850153490972,0.5686274509803921
base,v125_top3_lb14_quality,10,-13.544683392359559,0.5

## Rescue Weight Summary

position_weight,trade_count,total_net_pnl_bps,win_rate
2.9,101,9755.618103846386,0.6435643564356436
4.5,6,5683.350432647911,1.0

## Interpretation

V138 keeps the V137 weighted model ensemble and the V135 live structure: the same fixed UTC hour veto, the same realized drawdown guard, no daily trade cap, and no day-end ranking. It does not add or remove rescue events. The model-level change is confidence sizing: rescue events keep the base weight unless direction_probability is at least 0.66, in which case the rescue weight increases to 4.5. This is a research candidate, not a live trading guarantee.
