# Research V87 BTCUSDC Recent Repair Validation Results

## Decision

- Promote repair candidate: `True`
- Selected policy: `oversold_short_veto`
- Selected total improvement: `1128.831108` bps
- Selected recent improvement: `23.627063` bps
- Selected holdout improvement: `277.760540` bps

## Selected Policy

- Policy: `oversold_short_veto`
- Description: Skip short trades after a 24h lookback move below -650 bps.
- Trades: `175`
- Total net PnL: `5316.353438` bps
- Mean net PnL: `30.379163` bps
- Win rate: `0.554286`
- Positive fold rate: `1.000000`
- Worst fold: `393.829442` bps
- Holdout total: `1435.820712` bps
- Recent total: `646.065566` bps
- Recent active positive month rate: `0.600000`
- Tail active positive month rate: `0.666667`
- Latest active month: `2026-06`
- Latest active month PnL: `8.179728` bps

## Repair Candidates

policy,description,passed,failed_checks,short_term_passed,recent_passed,trade_count,total_net_pnl_bps,total_improvement_bps,holdout_total_net_pnl_bps,holdout_improvement_bps,recent_total_net_pnl_bps,recent_total_improvement_bps,recent_tail_active_positive_month_rate,latest_active_month,latest_active_month_net_pnl_bps
remove_utc_00_04,Remove the UTC 00-04 session that is negative in full V69 and heavily negative in recent months.,False,short_term_passed,False,True,134,4641.856845124968,454.33451512241027,1373.4713112674062,215.41113936028069,1060.7480501876407,438.309547065624,0.6666666666666666,2026-06,175.36559016768555
oversold_short_veto,Skip short trades after a 24h lookback move below -650 bps.,True,,True,True,175,5316.35343838643,1128.8311083838726,1435.8207119668862,277.7605400597606,646.0655662340466,23.627063112029873,0.6666666666666666,2026-06,8.179727786607444
session_plus_oversold_short_veto,Remove UTC 00-04 and skip short trades after a 24h lookback move below -650 bps.,False,short_term_passed,False,True,128,5348.562973886381,1161.0406438838236,1746.145442762451,588.0852708553255,1009.0945220522867,386.65601893026997,0.6666666666666666,2026-06,175.36559016768555
keep_core_recent_sessions,"Keep UTC 06-11, 15, 17-19, and 21-22 only.",False,short_term_passed;holdout_not_worse,False,True,123,4443.129267100077,255.60693709752013,775.119389093684,-382.9407828134415,1060.7480501876407,438.309547065624,0.6666666666666666,2026-06,175.36559016768555

## Selected Recent Months

month,trades,total_net_pnl_bps,mean_net_pnl_bps,win_rate,positive
2026-01,3,63.54052299528283,21.18017433176094,0.3333333333333333,True
2026-02,8,-8.883458552410843,-1.1104323190513554,0.5,False
2026-03,5,677.7378121477659,135.54756242955318,0.8,True
2026-04,1,-94.50903814319882,-94.50903814319882,0.0,False
2026-06,3,8.179727786607444,2.726575928869148,0.3333333333333333,True

## Interpretation

V87 tests pre-trade repair candidates for the V69 12-hour short-term BTCUSDC candidate. The selected repair skips shorts after a deep 24-hour down move. This directly targets the recent deterioration source without using outcome-only fields.

The selected repair improves total, holdout, delay, cost, and recent-month behavior in the current evidence. It should still be treated as a repaired research candidate, not a live-profit guarantee, because the repair was motivated by observed recent deterioration and needs fresh forward monitoring.
