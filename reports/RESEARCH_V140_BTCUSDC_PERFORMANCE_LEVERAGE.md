# Research V140 BTCUSDC Performance Leverage

## Decision

- V139 selected account return: `648.857702%`
- V139 selected max drawdown: `-16.403174%`
- Required V139 improvement rate: `2.000000`
- V140 selected account return: `1351.394223%`
- V140 selected max drawdown: `-48.008947%`
- Trade count: `645`
- Positive months: `24/24`
- Worst month: `0.070202%`
- Fixed account leverage: `3.000000`
- V140 performance gate passed: `True`
- Status: `performance_leverage_candidate_found`

## Fixed Leverage Comparison

policy,trade_count,total_account_return_pct,max_drawdown_pct,positive_months,month_count,worst_month_pct,avg_account_leverage,max_account_leverage,levered_win_rate,fixed_leverage
fixed_1x,645,450.46474101339925,-16.002982488124644,24,24,0.023400565108359223,1.0,1.0,0.6062015503875969,1.0
fixed_2x,645,900.9294820267985,-32.00596497624929,24,24,0.046801130216718445,2.0,2.0,0.6062015503875969,2.0
fixed_3x,645,1351.3942230401976,-48.008947464373705,24,24,0.0702016953250777,3.0,3.0,0.6062015503875969,3.0
fixed_4x,645,1801.858964053597,-64.01192995249858,24,24,0.09360226043343689,4.0,4.0,0.6062015503875969,4.0
fixed_5x,645,2252.3237050669964,-80.014912440623,24,24,0.11700282554179653,5.0,5.0,0.6062015503875969,5.0

## Monthly Account Return

month,account_return_pct
2024-07,6.059737600773657
2024-08,13.02394638780433
2024-09,0.09129739538720427
2024-10,2.1900692296503714
2024-11,70.43043575353032
2024-12,217.4537865897261
2025-01,55.278757086898345
2025-02,57.43285817274743
2025-03,59.422737326263196
2025-04,3.1044409043657035
2025-05,10.613344169522302
2025-06,1.3894160986657498
2025-07,4.932852446680452
2025-08,0.4782326072983087
2025-09,0.0702016953250777
2025-10,302.2852730584324
2025-11,94.72406951982614
2025-12,17.440278571377238
2026-01,4.337519164317334
2026-02,240.82488585917363
2026-03,40.734112604741675
2026-04,12.754427632502912
2026-05,0.13059267008693812
2026-06,136.19095049510094

## Selected Account Return By Indicator

indicator_key,trade_count,account_return_pct,win_rate
v122_drought,84,771.5888100876584,0.6785714285714286
rescue_low_0p60_0p62,62,191.1252902291137,0.6774193548387096
rescue_high_ge_0p66,5,141.83711001784627,1.0
rescue_mid_0p62_0p66,28,116.48312310376912,0.6785714285714286
v123_threshold,45,55.66088740218339,0.6888888888888889
v120_peak,114,39.349293404798345,0.5614035087719298
v125_top7_lb14_coverage,246,31.020294250552023,0.5650406504065041
v125_top5_lb14_strict,51,4.735755046047293,0.5686274509803921
v125_top3_lb14_quality,10,-0.4063405017707864,0.5

## Research Notes

- External research review pointed to volatility targeting, fractional Kelly, and confidence sizing as common position-sizing approaches for crypto systems.
- The local V139 scan showed the balanced indicator leverage path reached about 648.86% account return with about -16.40% max drawdown.
- The fixed 3x overlay is the highest simple fixed leverage that keeps all 24 months positive while staying inside the aggressive -50% drawdown cap.
- 4x and 5x produce higher account-return estimates, but drawdown expands to about -64% and -80%, so they are reported but not promoted.

## Interpretation

V140 does not change V138/V139 trade selection, model signals, daily caps, or day-end ranking. It is an aggressive account-level leverage overlay selected for performance. This is a research candidate, not a live trading guarantee, and the leverage rows are account-return approximations rather than exchange liquidation guarantees.
