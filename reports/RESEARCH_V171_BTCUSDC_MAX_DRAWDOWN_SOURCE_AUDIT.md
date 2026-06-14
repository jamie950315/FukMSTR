# Research V171 BTCUSDC Max Drawdown Source Audit

## Decision

- Status: `max_drawdown_source_audit_ready`
- Promote to live: `False`
- Max drawdown: `-32.48404826334854` pct
- Peak timestamp: `2026-02-02 03:40:00+00:00`
- Trough timestamp: `2026-02-03 18:30:00+00:00`
- Window trade count: `6`
- Window return: `-32.48404826334857` pct
- Dominant loss group: `long`
- Message: Max-drawdown trades are attributed by source, side, leg, and execution mode for risk research only.

## Audit Rules

- Base path: V162 selected account path.
- Execution mode: V168 monthly execution readiness gate.
- Max drawdown window: trades after the latest equity peak through the max-drawdown trough.
- This audit does not add trades, change side, change thresholds, or promote live trading.

## Window Summary

max_drawdown_pct,peak_timestamp,trough_timestamp,window_start_timestamp,window_trade_count,window_return_pct
-32.48404826334854,2026-02-02 03:40:00+00:00,2026-02-03 18:30:00+00:00,2026-02-03 17:15:00+00:00,6,-32.48404826334857

## Side Attribution

side,trade_count,account_return_pct,account_pnl_bps,loss_trade_count,win_trade_count,avg_account_leverage,avg_position_weight,avg_direction_probability,win_rate_pct,return_share_of_window_pct
long,6,-32.48404826334856,-3248.4048263348564,6,0,2.3333333333333335,2.2204438842160177,0.6133699133037649,0.0,100.0

## Leg Attribution

leg,trade_count,account_return_pct,account_pnl_bps,loss_trade_count,win_trade_count,avg_account_leverage,avg_position_weight,avg_direction_probability,win_rate_pct,return_share_of_window_pct
rescue,3,-21.198256366524873,-2119.825636652487,3,0,2.3333333333333335,2.9,0.6129115333763759,0.0,65.25743403245295
base,3,-11.285791896823692,-1128.5791896823691,3,0,2.3333333333333335,1.5408877684320352,0.6140574831948483,0.0,34.74256596754703

## Source Attribution

source,trade_count,account_return_pct,account_pnl_bps,loss_trade_count,win_trade_count,avg_account_leverage,avg_position_weight,avg_direction_probability,win_rate_pct,return_share_of_window_pct
v138_confidence_sized_weighted_family_rescue,3,-21.198256366524873,-2119.825636652487,3,0,2.3333333333333335,2.9,0.6129115333763759,0.0,65.25743403245295
v122_drought,1,-6.167678880012861,-616.7678880012861,1,0,1.25,2.595200630522413,,0.0,18.98679262514147
v120_peak,1,-2.7799409651174876,-277.99409651174875,1,0,3.5,1.277462674773693,0.6184415741448678,0.0,8.557864902122029
v123_threshold,1,-2.338172051693343,-233.81720516933433,1,0,2.25,0.75,0.6096733922448289,0.0,7.197908440283533

## Side Leg Attribution

side,leg,trade_count,account_return_pct,account_pnl_bps,loss_trade_count,win_trade_count,avg_account_leverage,avg_position_weight,avg_direction_probability,win_rate_pct,return_share_of_window_pct
long,rescue,3,-21.198256366524873,-2119.825636652487,3,0,2.3333333333333335,2.9,0.6129115333763759,0.0,65.25743403245295
long,base,3,-11.285791896823692,-1128.5791896823691,3,0,2.3333333333333335,1.5408877684320352,0.6140574831948483,0.0,34.74256596754703

## Source Side Leg Attribution

source,side,leg,trade_count,account_return_pct,account_pnl_bps,loss_trade_count,win_trade_count,avg_account_leverage,avg_position_weight,avg_direction_probability,win_rate_pct,return_share_of_window_pct
v138_confidence_sized_weighted_family_rescue,long,rescue,3,-21.198256366524873,-2119.825636652487,3,0,2.3333333333333335,2.9,0.6129115333763759,0.0,65.25743403245295
v122_drought,long,base,1,-6.167678880012861,-616.7678880012861,1,0,1.25,2.595200630522413,,0.0,18.98679262514147
v120_peak,long,base,1,-2.7799409651174876,-277.99409651174875,1,0,3.5,1.277462674773693,0.6184415741448678,0.0,8.557864902122029
v123_threshold,long,base,1,-2.338172051693343,-233.81720516933433,1,0,2.25,0.75,0.6096733922448289,0.0,7.197908440283533

## Execution Mode Attribution

execution_readiness_mode,live_gate_action,trade_count,account_return_pct,account_pnl_bps,loss_trade_count,win_trade_count,avg_account_leverage,avg_position_weight,avg_direction_probability,win_rate_pct,return_share_of_window_pct
taker_allowed,normal_cost_monitoring,6,-32.48404826334856,-3248.4048263348564,6,0,2.3333333333333335,2.2204438842160177,0.6133699133037649,0.0,100.0

## Interpretation

V171 identifies the realized trade cluster that caused the largest account drawdown. Use it to decide what specific risk hypothesis should be tested next. It is not a live-trading proof and does not change the promoted research path.

This is a research audit, not a live trading guarantee.
