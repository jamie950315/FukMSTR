# Research V159 BTCUSDC Base Trend Abs Boost

## Decision

- Status: `base_trend_abs_boost_passed`
- Promote to next model: `True`
- Message: Base trend-abs boost improved V158 by at least 2% without worsening selector/full/holdout risk gates.
- Selector period: `< 2026-01-01T00:00:00+00:00`
- Holdout period: `>= 2026-01-01T00:00:00+00:00`

## Research Input

- V159 promotes the best strict-gate candidate found by the post-V158 continuation scan.
- Boost: `base` trades where `trend_abs_1440_bps >= selector q0.8` use `1.1x` sizing on top of V158.
- The overlay does not add trades, change sides, or use holdout data to set the threshold.

## Baseline

policy,trade_count,total_account_return_pct,max_drawdown_pct,positive_months,month_count,worst_month_pct,win_rate
v158_full,645,2255.5487057887312,-32.48404826334854,24,24,0.0653714582135968,0.6062015503875969
v158_selector,470,1561.903649971289,-28.69875051863687,18,18,0.0653714582135968,0.6
v158_holdout,175,693.6450558174422,-32.48404826334856,6,6,0.2545636095945029,0.6228571428571429

## V159 Context Metrics

v159_bucket,trade_count,v158_account_return_pct,win_rate,avg_trend_abs_1440_bps,avg_prior_ret_1440_bps,avg_range_align_1440,avg_premium_abs_bps
base_trend_abs_boost,108,645.1691125264689,63.888888888888886,855.5782638252017,-424.0125271157657,-0.7163941058758688,5.039088888888888
unchanged,537,1610.3795932622622,59.96275605214153,320.61361256355366,-166.02523605150776,-0.6193842495474209,4.3852646182495345

## Selected Candidate

candidate,feature,segment,operator,quantile,threshold,modifier,changed_trade_count,changed_selector_count,changed_holdout_count,flag_trade_count,flag_selector_count,flag_holdout_count,baseline_trade_count,full_trade_count,full_return_pct,full_delta_return_pct,full_max_drawdown_pct,full_delta_drawdown_pct,full_worst_month_pct,full_delta_worst_month_pct,full_positive_months,full_month_count,full_win_rate,selector_trade_count,selector_return_pct,selector_delta_return_pct,selector_max_drawdown_pct,selector_delta_drawdown_pct,selector_worst_month_pct,selector_delta_worst_month_pct,selector_positive_months,selector_month_count,selector_win_rate,holdout_trade_count,holdout_return_pct,holdout_delta_return_pct,holdout_max_drawdown_pct,holdout_delta_drawdown_pct,holdout_worst_month_pct,holdout_delta_worst_month_pct,holdout_positive_months,holdout_month_count,holdout_win_rate
v159_base_trend_abs_boost,trend_abs_1440_bps,base,>=,0.8,594.2713026948154,1.1,108,83,25,108,83,25,645,645,2320.065617041378,64.51691125264688,-32.48404826334854,0.0,0.0653714582135968,0.0,24,24,0.6062015503875969,470,1595.0368389873456,33.133189016056576,-28.69875051863687,0.0,0.0653714582135968,0.0,18,18,0.6,175,725.0287780540323,31.383722236590074,-32.48404826334856,0.0,0.2545636095945029,0.0,6,6,0.6228571428571429

## Selected Monthly Account Return

month,account_return_pct
2024-07,0.43750232188858906
2024-08,24.39217308566017
2024-09,1.7544498894161125
2024-10,1.4127524629464623
2024-11,136.5382115601947
2024-12,431.73400149678423
2025-01,70.25267583163597
2025-02,119.14668869526787
2025-03,40.86852636273081
2025-04,4.469750389236645
2025-05,0.8710738937971712
2025-06,1.108511007045624
2025-07,2.9440146002943637
2025-08,0.7660745422061681
2025-09,0.0653714582135968
2025-10,608.6433884361734
2025-11,118.57062670363204
2025-12,31.061046250221896
2026-01,0.4234347198163634
2026-02,349.8742640517525
2026-03,61.99187396328629
2026-04,13.256497465419509
2026-05,0.2545636095945029
2026-06,299.2281442441631

## Interpretation

V159 suggests that V158 still under-sizes base trades when the prior 1440-minute absolute trend move is in the upper selector quantile. The improvement clears return, drawdown, worst-month, and positive-month gates across selector, holdout, and full periods.

This is a research audit, not a live trading guarantee.
