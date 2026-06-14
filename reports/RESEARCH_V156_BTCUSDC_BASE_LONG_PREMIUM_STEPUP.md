# Research V156 BTCUSDC Base Long Premium Stepup

## Decision

- Status: `base_long_premium_stepup_passed`
- Promote to next model: `True`
- Message: Base-long premium stepup improved V155 by at least 1% without worsening selector/full/holdout risk gates.
- Selector period: `< 2026-01-01T00:00:00+00:00`
- Holdout period: `>= 2026-01-01T00:00:00+00:00`

## Research Input

- V156 tests whether the already-promoted V155 calm-premium base-long zone was sized too conservatively.
- Stepup: trades with `v155_base_long_premium_flag` move from `1.075x` total sizing to `1.1x` total sizing.
- The overlay does not add trades, change sides, or set a new threshold.

## Baseline

policy,trade_count,total_account_return_pct,max_drawdown_pct,positive_months,month_count,worst_month_pct,win_rate
v155_full,645,2204.901835468696,-32.48404826334854,24,24,0.04657863701094722,0.6062015503875969
v155_selector,470,1523.5042558260507,-28.69875051863687,18,18,0.04657863701094722,0.6
v155_holdout,175,681.3975796426453,-32.48404826334856,6,6,0.22444795427188946,0.6228571428571429

## V156 Context Metrics

v156_bucket,trade_count,v155_account_return_pct,win_rate,avg_premium_abs_bps,avg_premium_crowd_follow_120d,avg_trend_abs_60_bps,avg_funding_z_120d
base_long_premium_stepup,251,1061.7278719695212,60.1593625498008,3.007809561752988,0.6956181868906142,144.2536343195913,0.3679356140278833
unchanged,394,1143.1739634991745,60.913705583756354,5.442001269035533,-0.4460128729926054,151.5027051582553,-0.19379937794644247

## Selected Candidate

candidate,source_flag,v155_total_modifier,v156_total_modifier,incremental_modifier,changed_trade_count,changed_selector_count,changed_holdout_count,flag_trade_count,flag_selector_count,flag_holdout_count,baseline_trade_count,full_trade_count,full_return_pct,full_delta_return_pct,full_max_drawdown_pct,full_delta_drawdown_pct,full_positive_months,full_month_count,full_worst_month_pct,full_win_rate,selector_trade_count,selector_return_pct,selector_delta_return_pct,selector_max_drawdown_pct,selector_delta_drawdown_pct,selector_positive_months,selector_month_count,selector_worst_month_pct,selector_win_rate,holdout_trade_count,holdout_return_pct,holdout_delta_return_pct,holdout_max_drawdown_pct,holdout_delta_drawdown_pct,holdout_positive_months,holdout_month_count,holdout_worst_month_pct,holdout_win_rate
v156_base_long_premium_stepup,v155_base_long_premium_flag,1.075,1.1,1.0232558139534884,251,191,60,251,191,60,645,645,2229.5931813284524,24.69134585975644,-32.48404826334854,0.0,24,24,0.014835245491340188,0.6062015503875969,470,1540.4871585558506,16.98290272979989,-28.69875051863687,0.0,18,18,0.014835245491340188,0.6,175,689.1060227726016,7.708443129956322,-32.48404826334856,0.0,6,6,0.06569019410546606,0.6228571428571429

## Selected Monthly Account Return

month,account_return_pct
2024-07,0.3037173052187099
2024-08,21.7836404509107
2024-09,1.5870832186485675
2024-10,1.4532176923726128
2024-11,121.91530636402388
2024-12,424.9746523145708
2025-01,67.86747899596006
2025-02,117.06375690570287
2025-03,39.45997841866228
2025-04,3.3039421282144383
2025-05,1.0189007859719295
2025-06,1.09388757785138
2025-07,3.0922904487117826
2025-08,0.7402662230257742
2025-09,0.014835245491340188
2025-10,592.6015364439297
2025-11,111.61703451878455
2025-12,30.595633517799158
2026-01,0.06569019410546606
2026-02,334.00688909083414
2026-03,59.196759624277824
2026-04,14.404551258979568
2026-05,0.4487089957483501
2026-06,280.98342360865627

## Interpretation

V156 suggests that the V155 calm-premium base-long expansion can tolerate a small additional sizing step. This is a narrow sizing change on an already-locked V155 flag, not a new entry rule.

This is a research audit, not a live trading guarantee.
