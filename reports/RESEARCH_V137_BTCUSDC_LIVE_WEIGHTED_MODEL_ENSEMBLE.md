# Research V137 BTCUSDC Live Weighted Model Ensemble

## Decision

- V135 total PnL: `42206.722568` bps
- V135 win rate: `0.599379`
- V135 max drawdown: `1600.298249` bps
- V135 worst month: `2025-09` `2.340057` bps
- V137 total PnL: `43365.441686` bps
- V137 win rate: `0.606202`
- V137 max drawdown: `1600.298249` bps
- Trade count: `645`
- Skipped by drawdown guard: `18`
- Positive months: `24/24`
- Worst month: `2025-09` `2.340057` bps
- V137 model-improvement gate passed: `True`
- Status: `weighted_model_ensemble_improvement_candidate_found`

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
2025-03,1955.1186510322934
2025-04,103.48136347885671
2025-05,329.5120327886268
2025-06,46.31386995552499
2025-07,164.42841488934843
2025-08,15.941086909943627
2025-09,2.340056510835918
2025-10,8643.670789933181
2025-11,3157.468983994205
2025-12,553.6251642424958
2026-01,144.583972143911
2026-02,8027.496195305787
2026-03,1357.803753491389
2026-04,254.24297224700985
2026-05,4.353089002897933
2026-06,4539.698349836697

## Source Summary

leg,source,trade_count,total_net_pnl_bps,win_rate
base,v122_drought,84,25719.627002921945,0.6785714285714286
rescue,v137_weighted_family_rescue_11_8_5,95,13300.485029997975,0.6947368421052632
base,v123_threshold,45,1855.362913406113,0.6888888888888889
base,v120_peak,114,1311.6431134932782,0.5614035087719298
base,v125_top7_lb14_coverage,246,1034.0098083517341,0.5650406504065041
base,v125_top5_lb14_strict,51,157.85850153490972,0.5686274509803921
base,v125_top3_lb14_quality,10,-13.544683392359559,0.5

## Interpretation

V137 keeps the V135 live structure: the same fixed UTC hour veto, the same realized drawdown guard, no daily trade cap, and no day-end ranking. The change is model-level only: the probability-floor rescue leg no longer uses equal family averaging; it weights the ma, price_context, and technical families as 11:8:5 before creating chronological rescue events. This is a research candidate, not a live trading guarantee.
