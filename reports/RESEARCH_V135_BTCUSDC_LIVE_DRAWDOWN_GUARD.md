# Research V135 BTCUSDC Live Drawdown Guard

## Decision

- V134 total PnL: `41785.121696` bps
- V134 max drawdown: `3281.035418` bps
- Required max drawdown: `<= 1640.517709` bps
- Required total PnL: `> 40000.000000` bps
- V135 total PnL: `42206.722568` bps
- V135 max drawdown: `1600.298249` bps
- Drawdown reduction: `0.512258`
- Trade count: `644`
- Skipped by guard: `18`
- Win rate: `0.599379`
- Positive months: `24/24`
- Worst month: `2025-09` `2.340057` bps
- V135 drawdown/profit gate passed: `True`
- Status: `drawdown_halved_profit_floor_candidate_found`

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
2025-03,1551.2672644320273
2025-04,103.48136347885671
2025-05,108.30973349382913
2025-06,46.31386995552499
2025-07,164.42841488934843
2025-08,15.941086909943627
2025-09,2.340056510835918
2025-10,8643.670789933181
2025-11,3022.5705320935053
2025-12,264.1580684301813
2026-01,93.50302313378445
2026-02,8111.653198445688
2026-03,1278.9343068124806
2026-04,190.73647975504247
2026-05,4.353089002897933
2026-06,4539.698349836697

## Source Summary

leg,source,trade_count,total_net_pnl_bps,mean_net_pnl_bps
base,v122_drought,84,25719.627002921945,306.18603574907075
rescue,v132_prob_floor_0.6_cool5,94,12141.765911348795,129.1677224611574
base,v123_threshold,45,1855.362913406113,41.23028696458029
base,v120_peak,114,1311.6431134932782,11.505641346432265
base,v125_top7_lb14_coverage,246,1034.0098083517341,4.203291903868838
base,v125_top5_lb14_strict,51,157.85850153490972,3.095264735978622
base,v125_top3_lb14_quality,10,-13.544683392359559,-1.354468339235956

## Interpretation

V135 lowers the V134 rescue weight, adds fixed UTC hour vetoes for 5 and 9, and applies a realized drawdown guard. The guard uses only already-booked strategy PnL: once drawdown reaches 1600 bps, it skips the rest of that UTC day and resumes the next day. This reaches the requested drawdown reduction while keeping total PnL above 40000 bps, but remains a research candidate rather than a live trading guarantee.
