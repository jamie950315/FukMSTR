# Research V155 BTCUSDC Base Long Premium Expansion

## Decision

- Status: `base_long_premium_expansion_passed`
- Promote to next model: `True`
- Message: Base-long premium expansion improved V154 by at least 3% without worsening selector/full/holdout risk gates.
- Selector period: `< 2026-01-01T00:00:00+00:00`
- Holdout period: `>= 2026-01-01T00:00:00+00:00`

## Research Input

- V155 tests whether the calm-premium base-long zone can be modestly expanded on top of V154.
- Expansion: `base_long` trades where `premium_abs_bps <= selector q0.6` use `1.075x` sizing.
- The overlay does not add new trades. It only changes sizing on existing V154 trades.

## Baseline

policy,trade_count,total_account_return_pct,max_drawdown_pct,positive_months,month_count,worst_month_pct,win_rate
v154_full,645,2130.8277978894266,-32.48404826334854,24,24,0.14180881156976743,0.6062015503875969
v154_selector,470,1472.5555476366512,-28.69875051863687,18,18,0.14180881156976743,0.6
v154_holdout,175,658.2722502527761,-32.48404826334856,6,6,0.45603165368936516,0.6228571428571429

## V155 Context Metrics

v155_bucket,trade_count,v154_account_return_pct,win_rate,avg_premium_abs_bps,avg_premium_crowd_follow_120d,avg_trend_abs_60_bps
base_long_premium_expansion,251,987.6538343902523,60.1593625498008,3.007809561752988,0.6956181868906142,144.2536343195913
unchanged,394,1143.1739634991745,60.913705583756354,5.442001269035533,-0.4460128729926054,151.5027051582553

## Selected Candidate

candidate,feature,segment,operator,quantile,threshold,modifier,changed_trade_count,changed_selector_count,changed_holdout_count,flag_trade_count,flag_selector_count,flag_holdout_count,baseline_trade_count,full_trade_count,full_return_pct,full_delta_return_pct,full_max_drawdown_pct,full_delta_drawdown_pct,full_positive_months,full_month_count,full_worst_month_pct,full_win_rate,selector_trade_count,selector_return_pct,selector_delta_return_pct,selector_max_drawdown_pct,selector_delta_drawdown_pct,selector_positive_months,selector_month_count,selector_worst_month_pct,selector_win_rate,holdout_trade_count,holdout_return_pct,holdout_delta_return_pct,holdout_max_drawdown_pct,holdout_delta_drawdown_pct,holdout_positive_months,holdout_month_count,holdout_worst_month_pct,holdout_win_rate
v155_base_long_premium_expansion,premium_abs_bps,base_long,<=,0.6,4.926200000000001,1.075,251,191,60,251,191,60,645,645,2204.901835468696,74.07403757926932,-32.48404826334854,0.0,24,24,0.04657863701094722,0.6062015503875969,470,1523.5042558260507,50.94870818939944,-28.69875051863687,0.0,18,18,0.04657863701094722,0.6,175,681.3975796426453,23.125329389869194,-32.48404826334856,0.0,6,6,0.22444795427188946,0.6228571428571429

## Selected Monthly Account Return

month,account_return_pct
2024-07,0.40568746220931307
2024-08,21.09431348279889
2024-09,1.6096019813977207
2024-10,1.4714494248353602
2024-11,120.06925613730222
2024-12,418.03290985973405
2025-01,66.81187868916646
2025-02,116.49501047295479
2025-03,38.7680451557729
2025-04,3.1041104563679625
2025-05,0.9463179574943223
2025-06,1.0944976373572128
2025-07,2.9947392477284076
2025-08,0.6643709161623067
2025-09,0.04657863701094722
2025-10,589.1210274042759
2025-11,110.19825480183218
2025-12,30.576206101649564
2026-01,0.22444795427188946
2026-02,330.681337716292
2026-03,58.86425946746191
2026-04,14.37280841260266
2026-05,0.4505396602336036
2026-06,276.80418643178314

## Interpretation

V155 suggests that V154 still under-sizes a broad base-long calm-premium zone. This is a sizing expansion only: it does not add entries, change sides, or use holdout data to set the threshold.

This is a research audit, not a live trading guarantee.
