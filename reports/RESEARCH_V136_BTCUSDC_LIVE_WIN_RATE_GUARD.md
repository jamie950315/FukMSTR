# Research V136 BTCUSDC Live Win Rate Guard

## Decision

- V135 total PnL: `42206.722568` bps
- V135 win rate: `0.599379`
- V135 max drawdown: `1600.298249` bps
- V135 worst month: `2025-09` `2.340057` bps
- Required win rate: `> 0.620000`
- V136 total PnL: `43765.460819` bps
- V136 win rate: `0.623116`
- V136 max drawdown: `1563.617134` bps
- Trade count: `597`
- Skipped by drawdown guard: `18`
- Positive months: `24/24`
- Worst month: `2024-09` `3.043247` bps
- V136 no-degrade/win-rate gate passed: `True`
- Status: `win_rate_gt_62_no_v135_degrade_candidate_found`

## Monthly PnL

month,weighted_net_pnl_bps
2024-07,215.24507935170084
2024-08,434.1315462601444
2024-09,3.043246512906819
2024-10,108.90449545941232
2024-11,2330.697513851126
2024-12,7653.249861858189
2025-01,1842.625236229945
2025-02,2056.6963739232583
2025-03,1993.5710338686895
2025-04,102.20213689692102
2025-05,88.77842081980812
2025-06,46.31386995552499
2025-07,223.9378052573672
2025-08,101.00345806028186
2025-09,67.17341708621834
2025-10,8766.42453349847
2025-11,3028.8306864368114
2025-12,268.1034325262932
2026-01,81.30368092138146
2026-02,8224.479947791446
2026-03,1314.246190715632
2026-04,205.86288812301277
2026-05,42.17331642538307
2026-06,4566.462647600078

## Source Summary

leg,source,trade_count,total_net_pnl_bps,win_rate
base,v122_drought,83,25723.574270770227,0.6867469879518072
rescue,v132_prob_floor_0.6_cool5,93,12623.46210111501,0.6559139784946236
base,v123_threshold,40,2238.1572688316005,0.75
base,v120_peak,103,1871.5738920166086,0.6019417475728155
base,v125_top7_lb14_coverage,221,1114.1551994038641,0.579185520361991
base,v125_top5_lb14_strict,48,180.33510464538307,0.6041666666666666
base,v125_top3_lb14_quality,9,14.202982647306364,0.5555555555555556

## Interpretation

V136 keeps the V135 live structure and adds a fixed current-hour confidence guard. UTC hour 3 is fully vetoed. UTC hour 17 keeps base trades only when same-timestamp consensus_count is 2, or when the base source is v125_top7_lb14_coverage with prior_source_mean_bps at least 12. The probability-floor rescue leg remains additive, fixed-weight, chronological, and is not selected by day-end ranking or a daily trade cap. This is a research candidate, not a live trading guarantee.
