# Research V164 BTCUSDC V162 Robustness Audit

## Decision

- Status: `v162_robustness_warning`
- Promote to live: `False`
- Message: V162 did not pass every required robustness check; keep it as research-only.
- Required extra-cost max: `4.0` bps
- Required extra-cost passed: `False`
- Base overlay replay passed: `True`

## Audit Rules

- Base robustness path: V162 selected account path.
- Extra cost is added on top of V162 as `extra_cost_bps * account_leverage * position_weight` account bps per trade.
- Threshold sensitivity replays the V162 long trend-follow overlay from V161 with threshold offsets.
- Modifier sensitivity replays the V162 overlay from V161 with nearby sizing values.
- This audit does not add trades, change sides, or promote a live-trading system.

## Baseline

scenario_type,scenario_value,trade_count,full_return_pct,full_max_drawdown_pct,full_worst_month_pct,full_positive_months,full_month_count,full_win_rate,selector_return_pct,selector_max_drawdown_pct,selector_worst_month_pct,selector_positive_months,selector_month_count,selector_win_rate,holdout_return_pct,holdout_max_drawdown_pct,holdout_worst_month_pct,holdout_positive_months,holdout_month_count,holdout_win_rate,passed_scenario
baseline_v162,0.0,645,2415.387400509261,-32.48404826334854,0.19715181100921397,24,24,0.6062015503875969,1634.8543347944433,-28.69875051863687,0.19715181100921397,18,18,0.6,780.5330657148182,-32.48404826334856,0.7321121743423837,6,6,0.6228571428571429,True

## Extra Cost Sensitivity

scenario_type,scenario_value,trade_count,full_return_pct,full_max_drawdown_pct,full_worst_month_pct,full_positive_months,full_month_count,full_win_rate,selector_return_pct,selector_max_drawdown_pct,selector_worst_month_pct,selector_positive_months,selector_month_count,selector_win_rate,holdout_return_pct,holdout_max_drawdown_pct,holdout_worst_month_pct,holdout_positive_months,holdout_month_count,holdout_win_rate,passed_scenario
extra_cost_bps,0.0,645,2415.387400509261,-32.48404826334854,0.1971518110092173,24,24,0.6062015503875969,1634.8543347944428,-28.69875051863687,0.1971518110092173,18,18,0.6,780.5330657148183,-32.48404826334857,0.7321121743423837,6,6,0.6228571428571429,True
extra_cost_bps,2.0,645,2365.94047382269,-33.30838246212011,-1.3550805450180476,18,24,0.5922480620155038,1600.4660521044377,-30.514912309823103,-1.1908013002143436,14,18,0.5872340425531914,765.4744217182523,-33.308382462120264,-1.3550805450180476,4,6,0.6057142857142858,False
extra_cost_bps,4.0,645,2316.4935471361187,-37.99781451892159,-3.4499381722174114,18,24,0.5844961240310077,1566.0777694144322,-37.99781451892159,-2.578754411437902,14,18,0.5808510638297872,750.4157777216863,-34.62594908495349,-3.4499381722174114,4,6,0.5942857142857143,False
extra_cost_bps,8.0,645,2217.599693762976,-53.1336637514313,-7.639653426616138,16,24,0.5612403100775194,1497.301204034422,-53.1336637514313,-5.354660633885025,12,18,0.5574468085106383,720.2984897285542,-37.26108233061994,-7.639653426616138,4,6,0.5714285714285714,False
extra_cost_bps,16.0,645,2019.8119870166909,-83.40536221645084,-16.01908393541359,13,24,0.5131782945736434,1359.7480732744007,-83.40536221645084,-10.906473078779268,9,18,0.502127659574468,660.06391374229,-45.51919042682364,-16.01908393541359,4,6,0.5428571428571428,False

## Threshold Sensitivity

scenario_type,scenario_value,trade_count,full_return_pct,full_max_drawdown_pct,full_worst_month_pct,full_positive_months,full_month_count,full_win_rate,selector_return_pct,selector_max_drawdown_pct,selector_worst_month_pct,selector_positive_months,selector_month_count,selector_win_rate,holdout_return_pct,holdout_max_drawdown_pct,holdout_worst_month_pct,holdout_positive_months,holdout_month_count,holdout_win_rate,passed_scenario,threshold,flag_trade_count
threshold_offset_bps,-100.0,645,2417.7214988554288,-32.48404826334854,0.22147205188913865,24,24,0.6062015503875969,1636.818592065802,-28.911729619260427,0.22147205188913865,18,18,0.6,780.9029067896263,-32.48404826334856,0.6784151239761798,6,6,0.6228571428571429,True,-129.0642030867616,141
threshold_offset_bps,-50.0,645,2416.4398167217973,-32.48404826334854,0.19715181100921353,24,24,0.6062015503875969,1635.652340225316,-28.911729619260427,0.19715181100921353,18,18,0.6,780.7874764964811,-32.48404826334856,0.7326193817913831,6,6,0.6228571428571429,True,-79.06420308676161,114
threshold_offset_bps,0.0,645,2415.387400509261,-32.48404826334854,0.19715181100921353,24,24,0.6062015503875969,1634.8543347944433,-28.69875051863687,0.19715181100921353,18,18,0.6,780.5330657148182,-32.48404826334856,0.7321121743423837,6,6,0.6228571428571429,True,-29.0642030867616,96
threshold_offset_bps,50.0,645,2407.2529294519786,-32.48404826334854,0.14664564745152486,24,24,0.6062015503875969,1628.5813856457871,-28.69875051863687,0.14664564745152486,18,18,0.6,778.6715438061913,-32.48404826334857,0.33661653493199467,6,6,0.6228571428571429,True,20.9357969132384,83
threshold_offset_bps,100.0,645,2406.430145129395,-32.48404826334854,0.05680381047352967,24,24,0.6062015503875969,1627.752031069308,-28.69875051863687,0.05680381047352967,18,18,0.6,778.678114060087,-32.48404826334857,0.33661653493199467,6,6,0.6228571428571429,True,70.93579691323839,73

## Modifier Sensitivity

scenario_type,scenario_value,trade_count,full_return_pct,full_max_drawdown_pct,full_worst_month_pct,full_positive_months,full_month_count,full_win_rate,selector_return_pct,selector_max_drawdown_pct,selector_worst_month_pct,selector_positive_months,selector_month_count,selector_win_rate,holdout_return_pct,holdout_max_drawdown_pct,holdout_worst_month_pct,holdout_positive_months,holdout_month_count,holdout_win_rate,passed_scenario,threshold,flag_trade_count
modifier,1.05,645,2403.4288057488666,-32.48404826334854,0.14319331098659938,24,24,0.6062015503875969,1625.7030842639974,-28.69875051863687,0.14319331098659938,18,18,0.6,777.7257214848692,-32.48404826334857,0.5343643546371888,6,6,0.6228571428571429,True,-29.0642030867616,96
modifier,1.1,645,2415.387400509261,-32.48404826334854,0.19715181100921353,24,24,0.6062015503875969,1634.8543347944433,-28.69875051863687,0.19715181100921353,18,18,0.6,780.5330657148182,-32.48404826334856,0.7321121743423837,6,6,0.6228571428571429,True,-29.0642030867616,96
modifier,1.15,645,2427.345995269656,-32.48404826334854,0.2511103110318277,24,24,0.6062015503875969,1644.0055853248887,-28.69875051863687,0.2511103110318277,18,18,0.6,783.3404099447673,-32.48404826334857,0.8931782754951246,6,6,0.6228571428571429,True,-29.0642030867616,96

## Interpretation

V164 audits whether the promoted research candidate is fragile to realistic execution headwinds and small parameter movement. It is a robustness report, not a new return-improving strategy.

This is a research audit, not a live trading guarantee.
