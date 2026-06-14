# Research V142 BTCUSDC High Confidence Rescue 5x

## Decision

- V140 account return: `1351.394223%`
- V140 max drawdown: `-48.008947%`
- V141 account return: `1195.887107%`
- V141 max drawdown: `-34.444637%`
- V142 selected account return: `1257.490241%`
- V142 selected max drawdown: `-34.444637%`
- V142 improvement vs V141: `1.051512`
- High-confidence 5x trades: `2`
- Positive months: `24/24`
- Worst month: `0.052651%`
- Avg / max / min account leverage: `2.662403` / `5.000000` / `1.250000`
- V142 gate passed: `True`
- Status: `high_confidence_rescue_5x_candidate_found`

## Rule

- Use 5x only for rescue trades with direction_probability >= 0.66 while prior realized account drawdown is above -5%.
- Use 3.5x for normal trades while prior realized account drawdown is above -5%.
- Use 2.25x once prior realized account drawdown is at or below -5%.
- Use 1.25x once prior realized account drawdown is at or below -15%.
- The current trade's leverage is decided before applying the current trade's PnL.

## Comparison

policy,total_account_return_pct,max_drawdown_pct,positive_months,month_count,avg_account_leverage,max_account_leverage
v140_fixed_3x,1351.3942230401976,-48.008947464373705,24,24,3.0,3.0
v141_drawdown_throttle,1195.8871066861761,-34.44463670675066,24,24,2.657751937984496,3.5
v142_high_confidence_rescue_5x,1257.4902405988096,-34.44463670675077,24,24,2.662403100775194,5.0

## Leverage Usage

account_leverage,high_confidence_rescue_5x,trade_count,account_return_pct,win_rate
1.25,False,142,177.92828854661556,0.6197183098591549
2.25,False,179,108.84342145826344,0.5307262569832403
3.5,False,322,765.3747508851527,0.639751552795031
5.0,True,2,205.34377970877787,1.0

## High Confidence 5x Trades

timestamp,indicator_key,direction_probability,weighted_net_pnl_bps,account_leverage,account_return_pct,drawdown_pct
2025-10-10 21:20:00+00:00,rescue_high_ge_0p66,0.6644753098991422,4028.920252540961,5.0,201.44601262704805,0.0
2025-12-26 02:25:00+00:00,rescue_high_ge_0p66,0.6664634107514512,77.95534163459651,5.0,3.897767081729825,0.0

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
2025-10,307.6261661630439
2025-11,59.18982796148202
2025-12,21.516321791125723
2026-01,0.3818923784510161
2026-02,181.18490780856902
2026-03,47.52313137219861
2026-04,9.031052163016597
2026-05,0.2405921729586856
2026-06,158.23345988335268

## Interpretation

V142 keeps the same V139/V141 trade list and does not add day-end ranking, daily caps, or new trade filters. It only lets the historical high-confidence rescue zone use 5x when the account is not already in drawdown defense. This is a research candidate, not a live trading guarantee.
