# Research V162 BTCUSDC Long Trend Follow Boost

## Decision

- Status: `long_trend_follow_boost_passed`
- Promote to next model: `True`
- Message: Long trend-follow boost improved V161 by at least 1% without worsening selector/full/holdout risk gates.
- Selector period: `< 2026-01-01T00:00:00+00:00`
- Holdout period: `>= 2026-01-01T00:00:00+00:00`

## Research Input

- V162 tests the only strict-gate non-leaky candidate found after V161 with at least 1% full-period improvement.
- Boost: `long` trades where `trend_follow_1440_bps >= selector q0.8` use `1.1x` sizing on top of V161.
- The overlay does not add trades, change sides, or use holdout data to set the threshold.
- Post-trade account-path fields such as `drawdown_pct` are excluded from promotion because they are not valid entry-time signals.

## Baseline

policy,trade_count,total_account_return_pct,max_drawdown_pct,positive_months,month_count,worst_month_pct,win_rate
v161_full,645,2391.4702109884715,-32.48404826334854,24,24,0.08923481096398522,0.6062015503875969
v161_selector,470,1616.5518337335518,-28.69875051863687,18,18,0.08923481096398522,0.6
v161_holdout,175,774.91837725492,-32.48404826334856,6,6,0.33661653493199467,0.6228571428571429

## V162 Context Metrics

v162_bucket,trade_count,v161_account_return_pct,win_rate,avg_direction_probability,avg_trend_follow_1440_bps,avg_prior_ret_1440_bps,avg_trend_abs_1440_bps,avg_day_sofar_count,avg_range_align_1440,avg_premium_abs_bps,avg_funding_abs_bps
long_trend_follow_boost,96,239.17189520789753,67.70833333333334,0.6220713233647509,249.83084037932238,249.83084037932238,252.70105344677305,171.25,0.1819300789208926,4.3801531250000005,1.0137625000000001
unchanged,549,2152.2983157805743,59.38069216757741,0.6185963251565694,-402.72916870903737,-289.494836729649,437.7279805261565,174.98360655737704,-0.7785886940217933,4.514779599271403,0.6389014571948998

## Selected Candidate

candidate,feature,segment,operator,quantile,threshold,modifier,changed_trade_count,changed_selector_count,changed_holdout_count,flag_trade_count,flag_selector_count,flag_holdout_count,v161_flag_overlap_count,v161_flag_overlap_rate,v160_flag_overlap_count,v160_flag_overlap_rate,baseline_trade_count,full_trade_count,full_return_pct,full_delta_return_pct,full_max_drawdown_pct,full_delta_drawdown_pct,full_worst_month_pct,full_delta_worst_month_pct,full_positive_months,full_month_count,full_win_rate,selector_trade_count,selector_return_pct,selector_delta_return_pct,selector_max_drawdown_pct,selector_delta_drawdown_pct,selector_worst_month_pct,selector_delta_worst_month_pct,selector_positive_months,selector_month_count,selector_win_rate,holdout_trade_count,holdout_return_pct,holdout_delta_return_pct,holdout_max_drawdown_pct,holdout_delta_drawdown_pct,holdout_worst_month_pct,holdout_delta_worst_month_pct,holdout_positive_months,holdout_month_count,holdout_win_rate
v162_long_trend_follow_boost,trend_follow_1440_bps,long,>=,0.8,-29.0642030867616,1.1,96,74,22,96,74,22,28,0.2916666666666667,6,0.0625,645,645,2415.387400509261,23.917189520789634,-32.48404826334854,0.0,0.19715181100921353,0.1079170000452283,24,24,0.6062015503875969,470,1634.8543347944433,18.302501060891473,-28.69875051863687,0.0,0.19715181100921353,0.1079170000452283,18,18,0.6,175,780.5330657148182,5.614688459898275,-32.48404826334856,0.0,0.7321121743423837,0.39549563941038907,6,6,0.6228571428571429

## Selected Monthly Account Return

month,account_return_pct
2024-07,0.19715181100921353
2024-08,25.425381042769118
2024-09,1.9000216866898654
2024-10,1.4988065081276383
2024-11,146.69262429672187
2024-12,435.2119934786595
2025-01,72.29325767511403
2025-02,122.05670474868053
2025-03,46.998454089635096
2025-04,5.135615806158352
2025-05,0.6349404227379305
2025-06,0.995410921529043
2025-07,3.090957404658764
2025-08,0.7933855825033861
2025-09,0.20422529568444892
2025-10,617.4045998990302
2025-11,122.00332461060664
2025-12,32.31747951412736
2026-01,0.7397770821813164
2026-02,376.7061535017615
2026-03,65.63438136096796
2026-04,13.723884638013788
2026-05,0.7321121743423837
2026-06,322.9967569575514

## Interpretation

V162 suggests that V161 still under-sizes long trades when the 1440-minute direction-following trend is in its upper selector quantile. The threshold is still slightly negative because it is selected from the long-trade distribution, so the practical meaning is less adverse or more supportive 1440-minute trend, not necessarily a strong breakout regime.

This is a research audit, not a live trading guarantee.
