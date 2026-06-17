# Research V90 BTCUSDC Forward Monitoring Results

## Decision

- Data end: `2026-06-15T23:59:00+00:00`
- Forward signal start: `2026-06-06T04:10:00+00:00`
- New aggTrade files: `5`
- New signal count across monitored policies: `0`
- Monitoring status: `no_signal`
- Next action: `continue_monitoring`

## Policy Monitoring

policy,status,monitoring_ok,trade_count,total_net_pnl_bps,mean_net_pnl_bps,win_rate,worst_delay_total_net_pnl_bps,required_extra_cost_total_net_pnl_bps,next_action
v69_v87_oversold_short_veto_-650,no_signal,True,0,0.0,0.0,0.0,0.0,0.0,continue_monitoring
v89_conservative_same_family_-550,no_signal,True,0,0.0,0.0,0.0,0.0,0.0,continue_monitoring
v89_mechanical_remove_hours_0_2_3_4,no_signal,True,0,0.0,0.0,0.0,0.0,0.0,continue_monitoring

## Interpretation

V90 extends the BTCUSDC aggTrade flow data through the newly available Binance public files and rebuilds the fixed V68/V69/V89 ledgers without changing thresholds.

There are no new signal timestamps after the V89 cutoff through the current data end. The delayed entries seen immediately after the cutoff belong to the old 2026-06-06 04:10 UTC signal, so they are excluded from forward monitoring.

This is a monitoring result, not a new profit proof. The correct action is to keep collecting new public files and rerun this monitor when more days are available.
