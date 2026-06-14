# Research V161 BTCUSDC Day Sofar Count Boost

## Decision

- Status: `day_sofar_count_boost_passed`
- Promote to next model: `True`
- Message: Low day-sofar-count boost improved V160 by at least 1% without worsening selector/full/holdout risk gates.
- Selector period: `< 2026-01-01T00:00:00+00:00`
- Holdout period: `>= 2026-01-01T00:00:00+00:00`

## Research Input

- V161 tests the best strict-gate low-overlap candidate found after V160.
- Boost: `all` trades where `day_sofar_count <= selector q0.3` use `1.05x` sizing on top of V160.
- The overlay does not add trades, change sides, or use holdout data to set the threshold.

## Baseline

policy,trade_count,total_account_return_pct,max_drawdown_pct,positive_months,month_count,worst_month_pct,win_rate
v160_full,645,2355.549918230334,-32.48404826334854,24,24,0.0653714582135968,0.6062015503875969
v160_selector,470,1613.2600929461773,-28.69875051863687,18,18,0.0653714582135968,0.6
v160_holdout,175,742.2898252841567,-32.48404826334856,6,6,0.2545636095945029,0.6228571428571429

## V161 Context Metrics

v161_bucket,trade_count,v160_account_return_pct,win_rate,avg_day_sofar_count,avg_day_sofar_max_prob,avg_direction_probability,avg_trend_abs_1440_bps,avg_prior_ret_1440_bps,avg_range_align_1440,avg_premium_abs_bps,avg_funding_abs_bps
day_sofar_count_boost,186,718.4058551627543,66.12903225806451,46.446236559139784,0.5300847017993199,0.6160335103450356,437.94452471826094,-235.5497868775043,-0.6015079613266079,4.27427311827957,0.6946586021505377
unchanged,459,1637.1440630675797,58.387799564270146,226.28976034858388,0.5574588679316358,0.6202192654770937,398.941788327132,-198.5547806730862,-0.6494540841716989,4.5840825708061,0.6947093681917211

## Selected Candidate

candidate,feature,segment,operator,quantile,threshold,modifier,changed_trade_count,changed_selector_count,changed_holdout_count,flag_trade_count,flag_selector_count,flag_holdout_count,v160_flag_overlap_count,v160_flag_overlap_rate,baseline_trade_count,full_trade_count,full_return_pct,full_delta_return_pct,full_max_drawdown_pct,full_delta_drawdown_pct,full_worst_month_pct,full_delta_worst_month_pct,full_positive_months,full_month_count,full_win_rate,selector_trade_count,selector_return_pct,selector_delta_return_pct,selector_max_drawdown_pct,selector_delta_drawdown_pct,selector_worst_month_pct,selector_delta_worst_month_pct,selector_positive_months,selector_month_count,selector_win_rate,holdout_trade_count,holdout_return_pct,holdout_delta_return_pct,holdout_max_drawdown_pct,holdout_delta_drawdown_pct,holdout_worst_month_pct,holdout_delta_worst_month_pct,holdout_positive_months,holdout_month_count,holdout_win_rate
v161_day_sofar_count_boost,day_sofar_count,all,<=,0.3,140.0,1.05,186,142,44,186,142,44,38,0.20430107526881722,645,645,2391.4702109884715,35.92029275813775,-32.48404826334854,0.0,0.089234810963987,0.0238633527503902,24,24,0.6062015503875969,470,1616.5518337335518,3.291740787374465,-28.69875051863687,0.0,0.089234810963987,0.0238633527503902,18,18,0.6,175,774.91837725492,32.62855197076328,-32.48404826334856,0.0,0.33661653493199467,0.08205292533749176,6,6,0.6228571428571429

## Selected Monthly Account Return

month,account_return_pct
2024-07,0.089234810963987
2024-08,25.425381042769118
2024-09,1.7751820152425517
2024-10,1.4177717772158749
2024-11,140.22567869854007
2024-12,433.50846442211855
2025-01,71.46849957446906
2025-02,121.42554932603642
2025-03,39.182280484806896
2025-04,5.273424116593077
2025-05,1.134601275334727
2025-06,0.9840387513002504
2025-07,3.0925813423745754
2025-08,0.8362070329594832
2025-09,0.09694278041447191
2025-10,617.3734548849694
2025-11,121.78576882928435
2025-12,31.456772568158723
2026-01,0.4329746955536983
2026-02,374.668219291037
2026-03,62.759925137832134
2026-04,13.723884638013788
2026-05,0.33661653493199467
2026-06,322.9967569575514

## Interpretation

V161 suggests that V160 under-sizes trades that appear earlier in the day's signal sequence. The edge is a small sizing improvement, not a new entry signal. It is also relatively low-overlap with the V160 trend-abs stepup flag, which makes it less likely to be only another repeat of the same prior boost.

This is a research audit, not a live trading guarantee.
