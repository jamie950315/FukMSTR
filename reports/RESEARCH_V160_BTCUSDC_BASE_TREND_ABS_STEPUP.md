# Research V160 BTCUSDC Base Trend Abs Stepup

## Decision

- Status: `base_trend_abs_stepup_passed`
- Promote to next model: `True`
- Message: Base trend-abs stepup improved V159 by at least 1% without worsening selector/full/holdout risk gates.
- Selector period: `< 2026-01-01T00:00:00+00:00`
- Holdout period: `>= 2026-01-01T00:00:00+00:00`

## Research Input

- V160 tests whether the already-promoted V159 base trend-abs zone can tolerate a small additional sizing step.
- Stepup: trades with `v159_base_trend_abs_boost_flag` use an additional `1.05x` sizing on top of V159.
- The overlay does not add trades, change sides, or set a new threshold.

## Baseline

policy,trade_count,total_account_return_pct,max_drawdown_pct,positive_months,month_count,worst_month_pct,win_rate
v159_full,645,2320.065617041378,-32.48404826334854,24,24,0.0653714582135968,0.6062015503875969
v159_selector,470,1595.0368389873456,-28.69875051863687,18,18,0.0653714582135968,0.6
v159_holdout,175,725.0287780540323,-32.48404826334856,6,6,0.2545636095945029,0.6228571428571429

## V160 Context Metrics

v160_bucket,trade_count,v159_account_return_pct,win_rate,avg_trend_abs_1440_bps,avg_prior_ret_1440_bps,avg_range_align_1440,avg_premium_abs_bps
base_trend_abs_stepup,108,709.6860237791159,63.888888888888886,855.5782638252017,-424.0125271157657,-0.7163941058758688,5.039088888888888
unchanged,537,1610.3795932622622,59.96275605214153,320.61361256355366,-166.02523605150776,-0.6193842495474209,4.3852646182495345

## Selected Candidate

candidate,source_flag,stepup_modifier,changed_trade_count,changed_selector_count,changed_holdout_count,flag_trade_count,flag_selector_count,flag_holdout_count,baseline_trade_count,full_trade_count,full_return_pct,full_delta_return_pct,full_max_drawdown_pct,full_delta_drawdown_pct,full_worst_month_pct,full_delta_worst_month_pct,full_positive_months,full_month_count,full_win_rate,selector_trade_count,selector_return_pct,selector_delta_return_pct,selector_max_drawdown_pct,selector_delta_drawdown_pct,selector_worst_month_pct,selector_delta_worst_month_pct,selector_positive_months,selector_month_count,selector_win_rate,holdout_trade_count,holdout_return_pct,holdout_delta_return_pct,holdout_max_drawdown_pct,holdout_delta_drawdown_pct,holdout_worst_month_pct,holdout_delta_worst_month_pct,holdout_positive_months,holdout_month_count,holdout_win_rate
v160_base_trend_abs_stepup,v159_base_trend_abs_boost_flag,1.05,108,83,25,108,83,25,645,645,2355.549918230334,35.48430118895567,-32.48404826334854,0.0,0.0653714582135968,0.0,24,24,0.6062015503875969,470,1613.2600929461773,18.22325395883172,-28.69875051863687,0.0,0.0653714582135968,0.0,18,18,0.6,175,742.2898252841567,17.261047230124404,-32.48404826334856,0.0,0.2545636095945029,0.0,6,6,0.6228571428571429

## Selected Monthly Account Return

month,account_return_pct
2024-07,0.5462012937694346
2024-08,25.605826375389704
2024-09,1.7544498894161125
2024-10,1.4127524629464623
2024-11,139.1748837048133
2024-12,433.56369147775393
2025-01,70.85804985132688
2025-02,119.67242952590651
2025-03,40.47489991778663
2025-04,5.184138931089257
2025-05,0.8518568458237048
2025-06,1.108511007045624
2025-07,2.9440146002943637
2025-08,0.7660745422061681
2025-09,0.0653714582135968
2025-10,616.0789618121293
2025-11,121.89460630486585
2025-12,31.303372945400323
2026-01,0.31298815790231094
2026-02,357.6889370936937
2026-03,62.00779888266163
2026-04,13.256497465419509
2026-05,0.2545636095945029
2026-06,308.76904007488514

## Interpretation

V160 suggests that the V159 base trend-abs flag can tolerate a small additional step-up. This is not a new signal; it is a narrow sizing adjustment on an already-locked flag.

This is a research audit, not a live trading guarantee.
