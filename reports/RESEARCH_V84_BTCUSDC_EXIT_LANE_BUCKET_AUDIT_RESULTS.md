# Research V84 BTCUSDC Exit/Lane Bucket Audit Results

## Decision

- Promote pretrade bucket: `False`
- Passed pretrade buckets: `0`
- Passed outcome buckets: `1`

## Gate

- Min trades: `50`
- Min total net PnL: `0.0` bps
- Min positive fold rate: `1.0`
- Min positive month rate: `1.0`
- Min win rate: `0.5`

## Buckets

bucket_column,bucket_value,bucket_type,trades,total_net_pnl_bps,mean_net_pnl_bps,win_rate,fold_count,positive_fold_rate,worst_fold_net_pnl_bps,month_count,positive_month_rate,worst_month_net_pnl_bps,passed,failed_checks
v24_core_lane,0,pretrade,888,-7975.777393862914,-8.981731299395173,0.18693693693693694,1,0.0,-7975.777393862914,30,0.0,-410.76061760275195,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
v24_rescue_lane,1,pretrade,888,-7975.777393862914,-8.981731299395173,0.18693693693693694,1,0.0,-7975.777393862914,30,0.0,-410.76061760275195,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
take_profit_bps,25.0,pretrade,1776,-14748.4110451844,-8.30428549841464,0.11317567567567567,2,0.0,-7400.663717999171,30,0.0,-650.4029007172163,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
take_profit_bps,20.0,pretrade,1776,-16041.446812054142,-9.032346177958413,0.1447072072072072,1,0.0,-16041.446812054144,30,0.0,-729.6881496806112,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
take_profit_bps,52.0,pretrade,2664,-23309.059422573308,-8.749646930395386,0.13551051051051052,3,0.0,-7975.777393862914,30,0.0,-940.7671986992167,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
take_profit_bps,45.0,pretrade,3552,-30138.047527360413,-8.484810677747864,0.147240990990991,3,0.0,-14797.348828083013,30,0.0,-1535.854513539023,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
hold_sec,120.0,pretrade,3504,-32361.465171427586,-9.235577959882303,0.1541095890410959,4,0.0,-8735.082785512248,30,0.0,-1331.737030794803,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
signal,1,pretrade,4440,-39350.50623462745,-8.862726629420596,0.13918918918918918,4,0.0,-16041.446812054144,30,0.0,-1602.97807838887,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
signal,-1,pretrade,5328,-44886.45857254481,-8.424635617970122,0.13588588588588588,4,0.0,-14797.348828083013,30,0.0,-2045.3868323920183,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
hold_sec,60.0,pretrade,6264,-51875.49963574468,-8.281529316051195,0.1280332056194125,5,0.0,-15182.994153704349,30,0.0,-1996.4618329016148,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
v24_core_lane,1,pretrade,8880,-76261.18741330935,-8.587971555552855,0.13243243243243244,5,0.0,-16041.446812054144,30,0.0,-3019.8047106165077,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
v24_rescue_lane,0,pretrade,8880,-76261.18741330935,-8.587971555552855,0.13243243243243244,5,0.0,-16041.446812054144,30,0.0,-3019.8047106165077,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
exit_reason,take_profit,outcome,163,2796.4999999999745,17.156441717791253,1.0,5,1.0,218.99999999999662,27,1.0,11.499999999999549,True,
exit_reason,horizon,outcome,9605,-87033.46480717225,-9.06126650777431,0.12274856845393024,5,0.0,-23320.30106141538,30,0.0,-3376.600259402221,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate

## Interpretation

V84 checks whether the V26 BTCUSDC full public replay has any stable pretrade subset among lane, side, take-profit size, or hold-time fields. It also shows exit_reason as an outcome-only bucket. Outcome buckets can explain losses, but they cannot be used as entry filters because they are only known after the trade exits.

The take_profit outcome bucket passes because winning take-profit exits are profitable by construction. No pretrade bucket passes. The result does not promote a strategy route and does not support another lane-only or exit-only rescue loop.
