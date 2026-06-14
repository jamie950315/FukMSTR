# Research V83 BTCUSDC Cost Edge Audit Results

## Decision

- Has passing cost scenario: `False`
- Best passing variant: `None`
- Best passing cost: `None`
- Original best passing cost: `None`
- Inverted best passing cost: `None`

## Gate

- Min total net PnL: `0.0` bps
- Min positive fold rate: `1.0`
- Min positive month rate: `1.0`
- Min win rate: `0.5`

## Cost Scenarios

variant,cost_bps,trades,total_net_pnl_bps,mean_net_pnl_bps,win_rate,fold_count,positive_fold_rate,worst_fold_net_pnl_bps,month_count,positive_month_rate,worst_month_net_pnl_bps,passed,failed_checks
original,0.0,9768,-1208.964807172265,-0.12376789590215653,0.4990786240786241,5,0.2,-945.4468120541445,30,0.43333333333333335,-370.4193234126789,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
original,0.05,9768,-1697.3648071722662,-0.17376789590215666,0.4964168714168714,5,0.2,-1034.2468120541448,30,0.43333333333333335,-387.46932341267893,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
original,0.1,9768,-2185.7648071722656,-0.2237678959021566,0.493959868959869,5,0.2,-1123.0468120541445,30,0.43333333333333335,-404.5193234126789,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
original,0.125,9768,-2429.9648071722654,-0.24876789590215656,0.4926289926289926,5,0.2,-1167.4468120541444,30,0.4,-413.0443234126789,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
original,0.25,9768,-3650.964807172265,-0.37376789590215653,0.4833128583128583,5,0.0,-1389.4468120541444,30,0.36666666666666664,-455.6693234126789,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
original,0.5,9768,-6092.964807172266,-0.6237678959021566,0.46744471744471744,5,0.0,-1833.4468120541444,30,0.16666666666666666,-540.9193234126789,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
original,1.0,9768,-10976.964807172266,-1.1237678959021566,0.4345823095823096,5,0.0,-2741.8010614153927,30,0.03333333333333333,-711.4193234126789,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
original,2.0,9768,-20744.964807172262,-2.1237678959021564,0.38001638001638,5,0.0,-5405.801061415393,30,0.0,-1052.419323412679,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
original,4.0,9768,-40280.96480717227,-4.123767895902157,0.27815315315315314,5,0.0,-10733.801061415392,30,0.0,-1734.419323412679,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
original,8.0,9768,-79352.96480717228,-8.123767895902157,0.14772727272727273,5,0.0,-21389.801061415394,30,0.0,-3098.4193234126788,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
original,8.5,9768,-84236.96480717228,-8.623767895902157,0.1373873873873874,5,0.0,-22721.801061415394,30,0.0,-3268.9193234126788,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
inverted,0.0,9768,1208.964807172265,0.12376789590215653,0.49795249795249796,5,0.8,-298.65117191698687,30,0.5666666666666667,-348.45711555587485,False,positive_fold_rate;positive_month_rate;win_rate
inverted,0.05,9768,720.5648071722642,0.07376789590215645,0.4954954954954955,5,0.4,-387.45117191698694,30,0.5,-364.9571155558749,False,positive_fold_rate;positive_month_rate;win_rate
inverted,0.1,9768,232.16480717226545,0.02376789590215658,0.49232186732186733,5,0.4,-476.25117191698683,30,0.5,-381.4571155558749,False,positive_fold_rate;positive_month_rate;win_rate
inverted,0.125,9768,-12.035192827734818,-0.0012321040978434498,0.4908886158886159,5,0.4,-520.6511719169869,30,0.5,-389.70711555587485,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
inverted,0.25,9768,-1233.0351928277346,-0.12623210409784344,0.4824938574938575,5,0.2,-742.6511719169869,30,0.36666666666666664,-430.9571155558749,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
inverted,0.5,9768,-3675.035192827735,-0.37623210409784347,0.46703521703521705,5,0.2,-1254.1989385846073,30,0.3,-513.4571155558749,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
inverted,1.0,9768,-8559.035192827736,-0.8762321040978436,0.4357084357084357,5,0.0,-2586.1989385846073,30,0.06666666666666667,-678.4571155558749,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
inverted,2.0,9768,-18327.035192827738,-1.8762321040978438,0.37919737919737917,5,0.0,-5250.198938584607,30,0.0,-1008.4571155558749,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
inverted,4.0,9768,-37863.03519282773,-3.876232104097843,0.2800982800982801,5,0.0,-10578.198938584608,30,0.0,-1668.457115555875,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
inverted,8.0,9768,-76935.03519282772,-7.876232104097842,0.15325552825552827,5,0.0,-21234.198938584606,30,0.0,-2988.4571155558747,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate
inverted,8.5,9768,-81819.03519282774,-8.376232104097843,0.14260851760851762,5,0.0,-22566.198938584606,30,0.0,-3153.4571155558747,False,total_net_pnl;positive_fold_rate;positive_month_rate;win_rate

## Interpretation

V83 separates gross signal edge from execution cost on the V26 BTCUSDC full public replay ledger. Original direction is negative even at zero added cost. Inverted direction is mildly positive at zero and very low cost, but it still fails fold and month stability, and it collapses before realistic taker cost.

The result does not promote a strategy route. The loss is cost-amplified, but there is no stable gross edge strong enough to justify deployment or another threshold-tuning loop.
