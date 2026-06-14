# Research V154 BTCUSDC Rescue Funding Stabilizer

## Decision

- Status: `rescue_funding_stabilizer_passed`
- Promote to next model: `True`
- Message: Rescue funding stabilizer improved V153 by at least 3% without worsening selector/full/holdout risk gates.
- Selector period: `< 2026-01-01T00:00:00+00:00`
- Holdout period: `>= 2026-01-01T00:00:00+00:00`

## Research Input

- V154 tests a fixed rescue funding boost plus premium stress stabilizer on top of V153.
- Boost: `rescue_long` trades where `funding_abs_z_30d <= selector q0.6` use `1.1x` sizing.
- Stabilizer: `base_long` trades where `premium_crowd_follow_120d <= selector q0.1` use `0.9x` sizing.
- The overlay does not add new trades. It only changes sizing on existing V153 trades.

## Baseline

policy,trade_count,total_account_return_pct,max_drawdown_pct,positive_months,month_count,worst_month_pct,win_rate
v153_full,645,2053.5052316763004,-32.79293059280599,24,24,0.2231094914194841,0.6062015503875969
v153_selector,470,1416.579884553997,-28.69875051863687,18,18,0.2231094914194841,0.6
v153_holdout,175,636.925347122304,-32.79293059280606,6,6,0.45603165368936516,0.6228571428571429

## V154 Context Metrics

v154_bucket,trade_count,v153_account_return_pct,win_rate,avg_funding_abs_z_30d,avg_premium_crowd_follow_120d
boost,42,761.6002156946801,78.57142857142857,0.37598920819164994,-0.1151978146736586
stabilizer,45,-11.62544643658154,51.11111111111111,1.3564048518224199,-2.3019161730370983
unchanged,558,1303.530462418202,60.0358422939068,1.0119498196527092,0.19228607339322712

## Selected Candidate

candidate,boost_feature,boost_segment,boost_operator,boost_quantile,boost_threshold,boost_modifier,stabilizer_feature,stabilizer_segment,stabilizer_operator,stabilizer_quantile,stabilizer_threshold,stabilizer_modifier,changed_trade_count,changed_selector_count,changed_holdout_count,boost_trade_count,boost_selector_count,boost_holdout_count,stabilizer_trade_count,stabilizer_selector_count,stabilizer_holdout_count,overlap_trade_count,baseline_trade_count,full_trade_count,full_return_pct,full_delta_return_pct,full_max_drawdown_pct,full_delta_drawdown_pct,full_positive_months,full_month_count,full_worst_month_pct,full_win_rate,selector_trade_count,selector_return_pct,selector_delta_return_pct,selector_max_drawdown_pct,selector_delta_drawdown_pct,selector_positive_months,selector_month_count,selector_worst_month_pct,selector_win_rate,holdout_trade_count,holdout_return_pct,holdout_delta_return_pct,holdout_max_drawdown_pct,holdout_delta_drawdown_pct,holdout_positive_months,holdout_month_count,holdout_worst_month_pct,holdout_win_rate
v154_rescue_funding_stabilizer,funding_abs_z_30d,rescue_long,<=,0.6,0.9576059634925392,1.1,premium_crowd_follow_120d,base_long,<=,0.1,-1.331428170239275,0.9,87,63,24,42,31,11,45,32,13,0,645,645,2130.8277978894266,77.32256621312627,-32.48404826334854,0.30888232945744676,24,24,0.14180881156976743,0.6062015503875969,470,1472.5555476366512,55.97566308265414,-28.69875051863687,0.0,18,18,0.14180881156976743,0.6,175,658.272250252776,21.346903130472015,-32.48404826334856,0.3088823294574965,6,6,0.45603165368936516,0.6228571428571429

## Selected Monthly Account Return

month,account_return_pct
2024-07,0.7115979331811213
2024-08,19.026332578463464
2024-09,1.6771582696451808
2024-10,1.5261446222235988
2024-11,114.53110545713731
2024-12,397.207682495224
2025-01,63.64507776878574
2025-02,114.78877117471055
2025-03,36.69224536710478
2025-04,2.504615440828532
2025-05,0.7285694720615028
2025-06,1.0963278158747103
2025-07,2.7020856447782844
2025-08,0.4366849955719043
2025-09,0.14180881156976743
2025-10,578.6795002853144
2025-11,105.94191565097508
2025-12,30.517923853200784
2026-01,0.7007212347711546
2026-02,320.7046835926655
2026-03,57.86675899701419
2026-04,14.277579873471936
2026-05,0.45603165368936516
2026-06,264.2664749011639

## Interpretation

V154 suggests that V153 rescue-long trades remain strongest when funding pressure is not extreme. It adds a small rescue boost in calm funding states and a small extra stabilizer to the already identified weak base-long premium crowd-follow zone.

This is a research audit, not a live trading guarantee.
