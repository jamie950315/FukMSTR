# Research V158 BTCUSDC Base Range Position Boost

## Decision

- Status: `base_range_position_boost_passed`
- Promote to next model: `True`
- Message: Base range-position boost improved V156 by at least 1% without worsening selector/full/holdout risk gates.
- Selector period: `< 2026-01-01T00:00:00+00:00`
- Holdout period: `>= 2026-01-01T00:00:00+00:00`

## Research Input

- V158 promotes the best strict-gate candidate found by V157.
- Boost: `base` trades where `prior_range_pos_1440 >= selector q0.6` use `1.1x` sizing on top of V156.
- The overlay does not add trades, change sides, or use holdout data to set the threshold.

## Baseline

policy,trade_count,total_account_return_pct,max_drawdown_pct,positive_months,month_count,worst_month_pct,win_rate
v156_full,645,2229.5931813284524,-32.48404826334854,24,24,0.01483524549134041,0.6062015503875969
v156_selector,470,1540.4871585558508,-28.69875051863687,18,18,0.01483524549134041,0.6
v156_holdout,175,689.1060227726016,-32.48404826334857,6,6,0.06569019410546606,0.6228571428571429

## V158 Context Metrics

v158_bucket,trade_count,v156_account_return_pct,win_rate,avg_prior_range_pos_1440,avg_prior_ret_1440_bps,avg_range_align_1440,avg_premium_abs_bps
base_range_position_boost,209,259.5552446027901,59.33014354066985,0.731413467931185,194.3059574248744,-0.2573995776403258,4.473766507177033
unchanged,436,1970.037936725662,61.23853211009175,0.11003089336866488,-402.65791236229614,-0.8169343892539697,4.504797018348624

## Selected Candidate

candidate,feature,segment,operator,quantile,threshold,modifier,changed_trade_count,changed_selector_count,changed_holdout_count,flag_trade_count,flag_selector_count,flag_holdout_count,baseline_trade_count,full_trade_count,full_return_pct,full_delta_return_pct,full_max_drawdown_pct,full_delta_drawdown_pct,full_worst_month_pct,full_delta_worst_month_pct,full_positive_months,full_month_count,full_win_rate,selector_trade_count,selector_return_pct,selector_delta_return_pct,selector_max_drawdown_pct,selector_delta_drawdown_pct,selector_worst_month_pct,selector_delta_worst_month_pct,selector_positive_months,selector_month_count,selector_win_rate,holdout_trade_count,holdout_return_pct,holdout_delta_return_pct,holdout_max_drawdown_pct,holdout_delta_drawdown_pct,holdout_worst_month_pct,holdout_delta_worst_month_pct,holdout_positive_months,holdout_month_count,holdout_win_rate
v158_base_range_position_boost,prior_range_pos_1440,base,>=,0.6,0.3366372319336817,1.1,209,165,44,209,165,44,645,645,2255.5487057887312,25.955524460278866,-32.48404826334854,0.0,0.0653714582135968,0.05053621272225639,24,24,0.6062015503875969,470,1561.9036499712888,21.41649141543803,-28.69875051863687,0.0,0.0653714582135968,0.05053621272225639,18,18,0.6,175,693.6450558174422,4.5390330448406075,-32.48404826334856,7.105427357601002e-15,0.25456360959450286,0.1888734154890368,6,6,0.6228571428571429

## Selected Monthly Account Return

month,account_return_pct
2024-07,0.2398678275597793
2024-08,22.18553074069738
2024-09,1.7544498894161125
2024-10,1.412752462946462
2024-11,131.74426220634265
2024-12,428.4072924404757
2025-01,69.15199579583432
2025-02,118.19079627592487
2025-03,41.58421080808388
2025-04,3.1708621313228083
2025-05,0.9060139810216539
2025-06,1.108511007045624
2025-07,2.9440146002943637
2025-08,0.7660745422061681
2025-09,0.0653714582135968
2025-10,595.1241641162536
2025-11,112.52702742866151
2025-12,30.620452258988394
2026-01,0.62424665056919
2026-02,335.66576761185934
2026-03,61.96291956442202
2026-04,13.256497465419509
2026-05,0.25456360959450286
2026-06,281.8810609155777

## Interpretation

V158 suggests that V156 still under-sizes base trades when the prior 1440-minute range position is in the upper selector quantile. The improvement is small, but it clears return, drawdown, worst-month, and positive-month gates across selector, holdout, and full periods.

This is a research audit, not a live trading guarantee.
