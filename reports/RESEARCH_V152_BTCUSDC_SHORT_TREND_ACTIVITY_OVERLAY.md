# Research V152 BTCUSDC Short Trend Activity Overlay

## Decision

- Status: `short_trend_activity_overlay_passed`
- Promote to next model: `True`
- Message: Short trend activity improved V151 without worsening holdout/full risk gates.
- Selector period: `< 2026-01-01T00:00:00+00:00`
- Holdout period: `>= 2026-01-01T00:00:00+00:00`

## Research Input

- V152 tests whether strict 60-minute trend activity can improve V151 sizing.
- The fixed hypothesis is `trend_abs_60_bps >= selector q0.85` with `1.05x` sizing.
- The threshold is calculated from the pre-2026 selector period. The 2026 holdout is reported after selection.
- The overlay does not add new trades. It only changes sizing on existing V151 trades.

## Baseline

policy,trade_count,total_account_return_pct,max_drawdown_pct,positive_months,month_count,worst_month_pct,win_rate
v151_full,645,1855.2700537582818,-34.40278472107207,24,24,0.32427023229671526,0.6062015503875969
v151_selector,470,1283.0369630854375,-28.69875051863687,18,18,0.32427023229671526,0.6
v151_holdout,175,572.2330906728446,-34.40278472107187,6,6,0.45603165368936516,0.6228571428571429

## Trend Activity Context Metrics

trend_abs_60_bucket,trade_count,account_return_pct,win_rate,avg_trend_abs_60_bps,avg_trend_follow_60_bps
"(0.686, 76.141]",129,73.33434307615612,55.03875968992248,49.89019998556114,-43.82585049948758
"(76.141, 108.105]",129,57.90019750186311,53.48837209302325,91.8410856625896,-91.8410856625896
"(108.105, 146.277]",129,38.02100799725889,65.89147286821705,125.14539153333243,-120.7586426252441
"(146.277, 209.566]",129,146.87202210852527,58.91472868217055,173.49538810060938,-148.60121036705635
"(209.566, 1107.694]",129,1539.1424830744784,69.76744186046511,303.03667926496183,-262.3129550239333

## Selected Candidate

candidate,feature,operator,quantile,threshold,multiplier,changed_trade_count,changed_selector_count,changed_holdout_count,full_trade_count,full_return_pct,full_delta_return_pct,full_max_drawdown_pct,full_delta_drawdown_pct,full_positive_months,full_month_count,full_worst_month_pct,full_win_rate,selector_trade_count,selector_return_pct,selector_delta_return_pct,selector_max_drawdown_pct,selector_delta_drawdown_pct,selector_positive_months,selector_month_count,selector_worst_month_pct,selector_win_rate,holdout_trade_count,holdout_return_pct,holdout_delta_return_pct,holdout_max_drawdown_pct,holdout_delta_drawdown_pct,holdout_positive_months,holdout_month_count,holdout_worst_month_pct,holdout_win_rate
boost1p05_trend_abs_60_bps_>=_q0p85,trend_abs_60_bps,>=,0.85,230.20237526923532,1.05,102,71,31,645,1933.0487191787727,77.77866542049082,-34.2547414408632,0.14804328020886715,24,24,0.32427023229671526,0.6062015503875969,470,1335.1283285365485,52.09136545111096,-28.69875051863687,0.0,18,18,0.32427023229671526,0.6,175,597.9203906422243,25.68729996937975,-34.25474144086281,0.148043280209059,6,6,0.45603165368936516,0.6228571428571429

## Selected Monthly Account Return

month,account_return_pct
2024-07,5.7074441520764605
2024-08,14.210302295003535
2024-09,0.8472003427600372
2024-10,1.592529146099657
2024-11,105.3251269115846
2024-12,396.6850730617891
2025-01,62.48491559192968
2025-02,110.3006470710808
2025-03,24.233924496712522
2025-04,2.5401270680286734
2025-05,1.4321940560781594
2025-06,1.0963278158747103
2025-07,2.3409320576756913
2025-08,0.32427023229671526
2025-09,0.5715409764896991
2025-10,478.11170960839553
2025-11,97.53076529272683
2025-12,29.79329835994589
2026-01,2.5988425212696886
2026-02,268.0847793814613
2026-03,56.64428908904343
2026-04,14.111965022809805
2026-05,0.45603165368936516
2026-06,256.0244829739507

## Top Selector Candidates

candidate,feature,operator,quantile,threshold,multiplier,changed_trade_count,changed_selector_count,changed_holdout_count,full_trade_count,full_return_pct,full_delta_return_pct,full_max_drawdown_pct,full_delta_drawdown_pct,full_positive_months,full_month_count,full_worst_month_pct,full_win_rate,selector_trade_count,selector_return_pct,selector_delta_return_pct,selector_max_drawdown_pct,selector_delta_drawdown_pct,selector_positive_months,selector_month_count,selector_worst_month_pct,selector_win_rate,holdout_trade_count,holdout_return_pct,holdout_delta_return_pct,holdout_max_drawdown_pct,holdout_delta_drawdown_pct,holdout_positive_months,holdout_month_count,holdout_worst_month_pct,holdout_win_rate
boost1p05_trend_abs_60_bps_>=_q0p85,trend_abs_60_bps,>=,0.85,230.20237526923532,1.05,102,71,31,645,1933.0487191787727,77.77866542049082,-34.2547414408632,0.14804328020886715,24,24,0.32427023229671526,0.6062015503875969,470,1335.1283285365485,52.09136545111096,-28.69875051863687,0.0,18,18,0.32427023229671526,0.6,175,597.9203906422243,25.68729996937975,-34.25474144086281,0.148043280209059,6,6,0.45603165368936516,0.6228571428571429

## Interpretation

V152 suggests the V151 signal is better sized when short-term movement is active enough. This is a modest sizing layer that improved holdout return and slightly improved max drawdown in the historical audit.

This is a research audit, not a live trading guarantee.
