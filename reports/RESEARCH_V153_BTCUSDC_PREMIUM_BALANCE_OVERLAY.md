# Research V153 BTCUSDC Premium Balance Overlay

## Decision

- Status: `premium_balance_overlay_passed`
- Promote to next model: `True`
- Message: Premium balance improved V152 by at least 5% without worsening selector/full/holdout risk gates.
- Selector period: `< 2026-01-01T00:00:00+00:00`
- Holdout period: `>= 2026-01-01T00:00:00+00:00`

## Research Input

- V153 tests a fixed two-part premium-basis sizing overlay on top of V152.
- Boost: `long` trades where `premium_abs_bps <= selector q0.2` use `1.15x` sizing.
- Throttle: `base_long` trades where `premium_crowd_follow_120d <= selector q0.1` use `0.7x` sizing.
- The overlay does not add new trades. It only changes sizing on existing V152 trades.

## Baseline

policy,trade_count,total_account_return_pct,max_drawdown_pct,positive_months,month_count,worst_month_pct,win_rate
v152_full,645,1933.0487191787727,-34.2547414408632,24,24,0.32427023229671526,0.6062015503875969
v152_selector,470,1335.1283285365485,-28.69875051863687,18,18,0.32427023229671526,0.6
v152_holdout,175,597.9203906422243,-34.2547414408628,6,6,0.45603165368936516,0.6228571428571429

## Premium Balance Context Metrics

v153_bucket,trade_count,v152_account_return_pct,win_rate,avg_premium_abs_bps,avg_premium_crowd_follow_120d
boost,90,769.8278554028107,60.0,1.3158966666666667,1.4609972829685323
throttle,45,-16.60778062368792,51.11111111111111,8.049964444444445,-2.3019161730370983
unchanged,510,1179.8286443996499,61.568627450980394,4.742018823529412,-0.056926342607923175

## Selected Candidate

candidate,boost_feature,boost_segment,boost_operator,boost_quantile,boost_threshold,boost_multiplier,throttle_feature,throttle_segment,throttle_operator,throttle_quantile,throttle_threshold,throttle_multiplier,changed_trade_count,changed_selector_count,changed_holdout_count,boost_trade_count,boost_selector_count,boost_holdout_count,throttle_trade_count,throttle_selector_count,throttle_holdout_count,overlap_trade_count,baseline_trade_count,full_trade_count,full_return_pct,full_delta_return_pct,full_max_drawdown_pct,full_delta_drawdown_pct,full_positive_months,full_month_count,full_worst_month_pct,full_win_rate,selector_trade_count,selector_return_pct,selector_delta_return_pct,selector_max_drawdown_pct,selector_delta_drawdown_pct,selector_positive_months,selector_month_count,selector_worst_month_pct,selector_win_rate,holdout_trade_count,holdout_return_pct,holdout_delta_return_pct,holdout_max_drawdown_pct,holdout_delta_drawdown_pct,holdout_positive_months,holdout_month_count,holdout_worst_month_pct,holdout_win_rate
v153_premium_balance_overlay,premium_abs_bps,long,<=,0.2,2.2866999999999997,1.15,premium_crowd_follow_120d,base_long,<=,0.1,-1.331428170239275,0.7,135,107,28,90,75,15,45,32,13,0,645,645,2053.5052316763004,120.45651249752768,-32.79293059280599,1.4618108480572118,24,24,0.2231094914194841,0.6062015503875969,470,1416.579884553997,81.45155601744864,-28.69875051863687,0.0,18,18,0.2231094914194841,0.6,175,636.925347122304,39.00495648007961,-32.79293059280606,1.4618108480567429,6,6,0.45603165368936516,0.6228571428571429

## Selected Monthly Account Return

month,account_return_pct
2024-07,1.3849120945331468
2024-08,18.151100387142687
2024-09,1.5201392023966402
2024-10,1.5261446222235988
2024-11,114.53110545713731
2024-12,397.207682495224
2025-01,63.60851755699345
2025-02,108.42097974678198
2025-03,32.550951843168306
2025-04,2.5823933461049933
2025-05,0.5240300327235319
2025-06,1.0963278158747103
2025-07,2.721568287715487
2025-08,0.5085371836362665
2025-09,0.2231094914194841
2025-10,540.2507238348188
2025-11,99.90207686889165
2025-12,29.869584287210493
2026-01,0.871985859887234
2026-02,306.08398614298136
2026-03,57.287787930773625
2026-04,14.277579873471936
2026-05,0.45603165368936516
2026-06,257.9479756615005

## Interpretation

V153 suggests the V152 signal benefits from treating premium basis as a sizing balance rather than a direction signal. Calm long premium conditions receive a modest boost, while weak base-long premium crowd-follow receives a throttle.

This is a research audit, not a live trading guarantee.
