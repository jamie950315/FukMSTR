# Research V141 BTCUSDC Drawdown Throttle Leverage

## Decision

- V139 account return: `648.857702%`
- V139 max drawdown: `-16.403174%`
- V140 account return: `1351.394223%`
- V140 max drawdown: `-48.008947%`
- V141 selected account return: `1195.887107%`
- V141 selected max drawdown: `-34.444637%`
- V141 return retained vs V140: `0.884928`
- V141 drawdown reduction vs V140: `0.282537`
- Positive months: `24/24`
- Worst month: `0.052651%`
- Avg / max / min account leverage: `2.657752` / `3.500000` / `1.250000`
- Throttled trades: `321`
- V141 gate passed: `True`
- Status: `drawdown_throttle_candidate_found`

## Rule

- Use 3.5x while prior realized account drawdown is above -5%.
- Use 2.25x once prior realized account drawdown is at or below -5%.
- Use 1.25x once prior realized account drawdown is at or below -15%.
- The current trade's leverage is decided before applying the current trade's PnL.

## Comparison

policy,total_account_return_pct,max_drawdown_pct,positive_months,month_count,avg_account_leverage,max_account_leverage
v139_indicator_leverage,648.8577022708914,-16.40317443585451,24,24,1.065891472868217,5.0
v140_fixed_3x,1351.3942230401976,-48.008947464373705,24,24,3.0,3.0
fixed_2p4x_reference,1081.1153784321582,-38.407157971499146,24,24,2.4,2.4
v141_drawdown_throttle,1195.8871066861761,-34.44463670675066,24,24,2.657751937984496,3.5

## Leverage Usage

account_leverage,trade_count,account_return_pct,win_rate
1.25,142,177.92828854661556,0.6197183098591549
2.25,179,108.84342145826344,0.5307262569832403
3.5,324,909.1153966812973,0.6419753086419753

## Monthly Account Return

month,account_return_pct
2024-07,2.991241353168955
2024-08,11.121501605403814
2024-09,0.0684730465404032
2024-10,1.64255192223778
2024-11,78.19071569723764
2024-12,249.3096851411521
2025-01,44.69866176514223
2025-02,64.52143040728504
2025-03,13.641678945066777
2025-04,1.2935170434857088
2025-05,2.251255598371145
2025-06,0.6714992111944901
2025-07,1.7493514413577937
2025-08,0.35867445547373145
2025-09,0.052651271493808105
2025-10,247.19236237492944
2025-11,59.18982796148202
2025-12,20.346991666606776
2026-01,0.3818923784510161
2026-02,181.18490780856902
2026-03,47.52313137219861
2026-04,9.031052163016597
2026-05,0.2405921729586856
2026-06,158.23345988335268

## Selected Account Return By Indicator

indicator_key,trade_count,account_return_pct,win_rate,avg_account_leverage
v122_drought,84,640.6942178884932,0.6785714285714286,2.3482142857142856
rescue_high_ge_0p66,5,156.31018902074368,1.0,2.35
rescue_low_0p60_0p62,62,155.75401601245576,0.6774193548387096,2.4556451612903225
rescue_mid_0p62_0p66,28,120.62788255091318,0.6785714285714286,2.125
v123_threshold,45,57.58417513951686,0.6888888888888889,2.827777777777778
v120_peak,114,33.966654991689005,0.5614035087719298,2.9934210526315788
v125_top7_lb14_coverage,246,26.739926505619994,0.5650406504065041,2.7266260162601625
v125_top5_lb14_strict,51,3.279583589079576,0.5686274509803921,2.6323529411764706
v125_top3_lb14_quality,10,0.9304609876650164,0.5,2.0

## Interpretation

V141 keeps the same V139/V140 trade list and does not add day-end ranking, daily caps, or new trade filters. It changes only the account-level leverage before each trade according to already-realized drawdown. This preserves most of V140's profit estimate while cutting the V140 drawdown by more than 25%. This is a research candidate, not a live trading guarantee.
