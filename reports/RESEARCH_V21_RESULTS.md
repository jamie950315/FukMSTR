# Research V21 Results

V21 continues from V20. The V20 BTC entry rule is frozen; V21 changes only the slot-preserving take-profit target from 40 bps to 45 bps.

## Plain summary

The current BTC contract rule still trades very rarely. On the bundled BTC sample it selected 10 trades and all 10 were winners after your real taker fee. V21 improves the profit target while keeping the same selected trade count and 100% selected-trade win rate on this sample.

## Frozen V21 policy

```text
V19 real-fee filters: unchanged
BTC side guard: long only, kline_15s_signal <= 0.0
short side: unchanged
real taker fee: 0.0400% per side = 4 bps per side
maker fee: 0.0000% per side, not promoted without a maker-fill proof
execution model: taker entry + taker exit
round-trip fee: 8 bps
horizon: 90 seconds
latency: 0.5 seconds
take profit: 45 bps
stop loss: disabled
reserved slot: enabled
promoted leverage cap: 3x research-only
```

## V20 vs V21

| Metric | V20 TP40 | V21 TP45 |
|---|---:|---:|
| Trades | 10.0000 | 10.0000 |
| Win rate | 1.0000 | 1.0000 |
| Mean net PnL bps/trade | 12.8764 | 13.4332 |
| Total net PnL bps | 128.7639 | 134.3322 |
| Worst fold total bps | 6.9553 | 6.9553 |
| Bootstrap mean p05 bps | 6.1083 | 6.1083 |
| Full stress min total bps | -0.718435 | 9.6268 |
| 50% missed-trade p05 total bps | 15.6448 | 15.7133 |
| Extra-cost gate total bps | 28.7639 | 14.3322 |

## V21 main gate

```json
{
  "passed": true,
  "checks": {
    "enough_trades": true,
    "hit_rate": true,
    "mean_profit": true,
    "total_profit": true,
    "fold_total_positive": true,
    "fold_mean_positive": true,
    "bootstrap_p05_positive": true,
    "selected_only_null": true,
    "side_exit_family_null": true,
    "fee_latency_stress_gate": true,
    "fee_latency_all_cells": true,
    "missed_trade_p05_positive": true,
    "extra_cost_positive": true,
    "promoted_leverage_buffer": true
  },
  "failed_checks": []
}
```

## Exit target family scan

take_profit_bps,events,trades,trade_rate,hit_rate,mean_net_pnl_bps,median_net_pnl_bps,total_net_pnl_bps,sharpe_like,max_drawdown_bps,profit_factor,mode,cost_bps,horizon_sec,latency_sec,stop_loss_bps,reserve_horizon,take_profit_exits,stop_loss_exits,horizon_exits,mean_hold_sec,fold_min_total_net_pnl_bps,fold_min_mean_net_pnl_bps,min_trade_net_pnl_bps
50.0,4910.0,10.0,0.0020366598778004,1.0,13.83083768053767,7.857928047136947,138.3083768053767,2.7265960106166807,0.0,inf,exit_lock_taker_bidask_non_overlap,8.0,90.0,0.5,0.0,True,1.0,0.0,9.0,88.1457,6.955256517678809,3.4776282588394043,0.7218522042499202
45.0,4910.0,10.0,0.0020366598778004,1.0,13.433223366422364,7.857928047136947,134.33223366422365,2.794335375516623,0.0,inf,exit_lock_taker_bidask_non_overlap,8.0,90.0,0.5,0.0,True,2.0,0.0,8.0,88.0456,6.955256517678809,3.4776282588394043,0.7218522042499202
40.0,4910.0,10.0,0.0020366598778004,1.0,12.876386201519017,7.857928047136947,128.76386201519014,2.8603728370510813,0.0,inf,exit_lock_taker_bidask_non_overlap,8.0,90.0,0.5,0.0,True,2.0,0.0,8.0,86.8327,6.955256517678809,3.4776282588394043,0.7218522042499202
0.0,4910.0,10.0,0.0020366598778004,1.0,11.922288972784193,7.857928047136947,119.2228897278419,2.9773113143119425,0.0,inf,exit_lock_taker_bidask_non_overlap,8.0,90.0,0.5,0.0,True,0.0,0.0,10.0,89.7145,6.955256517678809,3.4776282588394043,0.7218522042499202
55.0,4910.0,10.0,0.0020366598778004,1.0,11.922288972784193,7.857928047136947,119.2228897278419,2.9773113143119425,0.0,inf,exit_lock_taker_bidask_non_overlap,8.0,90.0,0.5,0.0,True,0.0,0.0,10.0,89.7145,6.955256517678809,3.4776282588394043,0.7218522042499202
60.0,4910.0,10.0,0.0020366598778004,1.0,11.922288972784193,7.857928047136947,119.2228897278419,2.9773113143119425,0.0,inf,exit_lock_taker_bidask_non_overlap,8.0,90.0,0.5,0.0,True,0.0,0.0,10.0,89.7145,6.955256517678809,3.4776282588394043,0.7218522042499202
35.0,4910.0,10.0,0.0020366598778004,1.0,11.285777123507566,7.857928047136947,112.85777123507566,3.2039449215047404,0.0,inf,exit_lock_taker_bidask_non_overlap,8.0,90.0,0.5,0.0,True,2.0,0.0,8.0,84.6155,6.955256517678809,3.4776282588394043,0.7218522042499202
25.0,4910.0,10.0,0.0020366598778004,1.0,10.249947169212422,8.26966798696931,102.49947169212422,3.737251908658246,0.0,inf,exit_lock_taker_bidask_non_overlap,8.0,90.0,0.5,0.0,True,4.0,0.0,6.0,81.7209,6.955256517678809,3.4776282588394043,0.7218522042499202
30.0,4910.0,10.0,0.0020366598778004,1.0,10.092807663203128,7.857928047136947,100.92807663203126,3.5115152689700238,0.0,inf,exit_lock_taker_bidask_non_overlap,8.0,90.0,0.5,0.0,True,2.0,0.0,8.0,84.46549999999999,6.955256517678809,3.4776282588394043,0.7218522042499202
20.0,4910.0,10.0,0.0020366598778004,1.0,8.266205440704042,8.651452884464355,82.66205440704042,4.134509871209314,0.0,inf,exit_lock_taker_bidask_non_overlap,8.0,90.0,0.5,0.0,True,5.0,0.0,5.0,72.34189999999998,6.955256517678809,3.4776282588394043,0.7218522042499202
15.0,4910.0,10.0,0.0020366598778004,1.0,5.805067999541453,6.242643520201167,58.05067999541453,4.813487943820108,0.0,inf,exit_lock_taker_bidask_non_overlap,8.0,90.0,0.5,0.0,True,5.0,0.0,5.0,66.54100000000001,6.955256517678809,3.4776282588394043,0.7218522042499202
10.0,4910.0,10.0,0.0020366598778004,1.0,3.5842648434647595,2.682608839051721,35.84264843464759,3.6745398142400103,0.0,inf,exit_lock_taker_bidask_non_overlap,8.0,90.0,0.5,0.0,True,8.0,0.0,2.0,60.94449999999999,4.579395267975791,2.2896976339878954,0.7218522042499202

V21 did not simply promote the highest total target. A 50 bps target has slightly higher base total, but it fails the full 10 bps-per-side / 5 second stress corner. The 45 bps target gives higher profit than V20 and keeps every stress cell positive.

## Fold results

fold,trades,hit_rate,mean_net_pnl_bps,total_net_pnl_bps
1,2,1.0,26.17438552307801,52.34877104615602
2,2,1.0,19.83803320616881,39.67606641233761
3,2,1.0,11.381105754139366,22.76221150827873
4,2,1.0,3.4776282588394043,6.955256517678809
5,2,1.0,6.294964089886225,12.58992817977245

## Stress result

The stress grid covers taker fees of 4, 5, 6, 7.5, and 10 bps per side, and latencies of 0, 0.5, 1, 2, 3, and 5 seconds. All 30 cells are positive under V21.

taker_fee_bps_per_side,roundtrip_fee_bps,latency_sec,events,trades,trade_rate,hit_rate,mean_net_pnl_bps,median_net_pnl_bps,total_net_pnl_bps,sharpe_like,max_drawdown_bps,profit_factor,mode,cost_bps,horizon_sec,take_profit_bps,stop_loss_bps,reserve_horizon,take_profit_exits,stop_loss_exits,horizon_exits,mean_hold_sec
10.0,20.0,5.0,4910.0,10.0,0.0020366598778004,0.3,0.9626814993115984,-5.726602101125341,9.626814993115984,0.2028519091074205,-29.690722222032267,1.1852864695563736,exit_lock_taker_bidask_non_overlap,20.0,90.0,45.0,0.0,True,2.0,0.0,8.0,83.5966

## Family-wise null correction

```json
{
  "selected_total_net_pnl_bps": 134.33223366422365,
  "selected_mean_net_pnl_bps": 13.433223366422364,
  "shift_null_runs": 1000,
  "candidate_count": 96,
  "side_candidate_count": 8,
  "exit_candidate_count": 12,
  "family_null_total_max_bps": 21.587301964756115,
  "family_null_mean_max_bps": 2.1587301964756116,
  "family_exceed_total_count": 0,
  "family_exceed_mean_count": 0,
  "family_addone_p_total_ge_selected": 0.000999000999000999,
  "family_addone_p_mean_ge_selected": 0.000999000999000999,
  "selected_only_null_total_max_bps": 21.587301964756115,
  "selected_only_null_mean_max_bps": 2.1587301964756116,
  "selected_only_exceed_total_count": 0,
  "selected_only_exceed_mean_count": 0,
  "selected_only_addone_p_total_ge_selected": 0.000999000999000999,
  "selected_only_addone_p_mean_ge_selected": 0.000999000999000999
}
```

## Leverage scenarios

leverage,notional_total_net_bps,notional_mean_net_bps,notional_min_trade_net_bps,approx_total_account_return_pct_no_compounding,approx_mean_account_return_pct_per_trade,approx_min_trade_account_return_pct,approx_liquidation_buffer_bps_before_safety_shock,shock_buffer_bps,passes_shock_buffer,notes
1.0,134.33223366422365,13.433223366422364,0.7218522042499202,1.3433223366422364,0.1343322336642236,0.0072185220424992,9942.0,250.0,True,"Approximation only; real liquidation depends on exchange bracket, mark price, cross/isolated margin, wallet balance, and open positions."
2.0,134.33223366422365,13.433223366422364,0.7218522042499202,2.686644673284473,0.2686644673284473,0.0144370440849984,4942.0,250.0,True,"Approximation only; real liquidation depends on exchange bracket, mark price, cross/isolated margin, wallet balance, and open positions."
3.0,134.33223366422365,13.433223366422364,0.7218522042499202,4.029967009926709,0.4029967009926709,0.0216555661274976,3275.333333333333,250.0,True,"Approximation only; real liquidation depends on exchange bracket, mark price, cross/isolated margin, wallet balance, and open positions."
5.0,134.33223366422365,13.433223366422364,0.7218522042499202,6.716611683211182,0.6716611683211182,0.036092610212496,1942.0,250.0,True,"Approximation only; real liquidation depends on exchange bracket, mark price, cross/isolated margin, wallet balance, and open positions."
10.0,134.33223366422365,13.433223366422364,0.7218522042499202,13.433223366422364,1.3433223366422364,0.072185220424992,942.0,250.0,True,"Approximation only; real liquidation depends on exchange bracket, mark price, cross/isolated margin, wallet balance, and open positions."
20.0,134.33223366422365,13.433223366422364,0.7218522042499202,26.86644673284473,2.686644673284473,0.144370440849984,442.0,250.0,True,"Approximation only; real liquidation depends on exchange bracket, mark price, cross/isolated margin, wallet balance, and open positions."

## Caveat

This is still a bundled-sample research result. It is stronger than V20 on this sample, but it still needs independent multi-day BTC contract validation before live-money use. Do not retune the V21 entry rule, side guard, or 45 bps target on validation days.
