# Research V81 BTCUSDC Fixed Family Viability Results

## Decision

- Promote fixed family: `False`
- Passed family count: `0`
- Failed checks: `no_family_passed`

## Gate

- Min active folds: `10`
- Min positive fold rate: `0.7`
- Min total account return pct: `0.0`
- Min worst fold account return pct: `-50.0`
- Min median fold account return pct: `0.0`

## Best Family

- lookback_minutes: `15`
- horizon_minutes: `240`
- direction: `momentum`
- filter_feature: `range_bps`
- quantile: `0.94`
- active_folds: `14`
- validation_trades: `339`
- total_validation_account_return_pct: `65.32121657505301`
- positive_fold_rate: `0.6428571428571429`
- worst_fold_account_return_pct: `-58.729595314710075`
- median_fold_account_return_pct: `1.6574637195951571`
- passed: `False`
- failed_checks: `positive_fold_rate;worst_fold_floor`

## Top Families

lookback_minutes,horizon_minutes,direction,filter_feature,quantile,active_folds,validation_trades,total_validation_net_pnl_bps,total_validation_account_return_pct,positive_fold_rate,worst_fold_account_return_pct,median_fold_account_return_pct,passed,meets_min_active_folds,failed_checks
15,240,momentum,range_bps,0.94,14,339,816.5152071881632,65.32121657505301,0.6428571428571429,-58.729595314710075,1.6574637195951571,False,True,positive_fold_rate;worst_fold_floor
30,240,flow_reversal,range_bps,0.7,14,584,1607.271875680587,128.58175005444696,0.6428571428571429,-63.18895846590698,8.752768340801008,False,True,positive_fold_rate;worst_fold_floor
60,240,reversal,range_bps,0.98,14,117,-1379.8096041307235,-110.38476833045789,0.6428571428571429,-180.3797885608566,5.867196231725712,False,True,positive_fold_rate;positive_total_account_return;worst_fold_floor
240,120,reversal,range_bps,0.98,10,101,428.96805738389116,34.31744459071129,0.6,-61.80762805027364,3.142767226990626,False,True,positive_fold_rate;worst_fold_floor
240,240,reversal,range_bps,0.98,10,61,228.04581464617877,18.243665171694303,0.6,-73.72947351596105,2.928620414113353,False,True,positive_fold_rate;worst_fold_floor
240,120,flow_reversal,abs_flow_imbalance,0.98,12,92,666.1470850715273,53.29176680572216,0.5833333333333334,-12.408693558360424,5.017199170330918,False,True,positive_fold_rate
120,60,flow_reversal,range_bps,0.98,12,166,-351.0734632005451,-28.0858770560436,0.5833333333333334,-44.227072498874165,2.0624763803651027,False,True,positive_fold_rate;positive_total_account_return
60,60,reversal,range_bps,0.98,14,219,1274.1999727047278,101.9359978163782,0.5714285714285714,-36.76935754443814,3.0382270356162597,False,True,positive_fold_rate
15,120,reversal,range_bps,0.98,14,294,-134.44814078345524,-10.755851262676433,0.5714285714285714,-43.40720103973081,1.5751212791626445,False,True,positive_fold_rate;positive_total_account_return
120,120,reversal,range_bps,0.85,14,433,754.1154956642201,60.329239653137634,0.5714285714285714,-57.05638357471743,5.5732064358870055,False,True,positive_fold_rate;worst_fold_floor
15,240,momentum,range_bps,0.98,14,214,1323.7330857338543,105.89864685870837,0.5714285714285714,-67.32679922433076,3.200127657073308,False,True,positive_fold_rate;worst_fold_floor
15,240,flow_momentum,range_bps,0.94,14,339,1497.8689064101627,119.82951251281301,0.5714285714285714,-83.29042632311173,1.1038540858587993,False,True,positive_fold_rate;worst_fold_floor
5,240,flow_reversal,volume_ratio,0.94,14,770,-2603.4173593197456,-208.27338874557972,0.5714285714285714,-134.41478334570797,3.8648401135585493,False,True,positive_fold_rate;positive_total_account_return;worst_fold_floor
30,240,momentum,range_bps,0.85,14,422,234.50318200601623,18.760254560481314,0.5714285714285714,-154.44463061500358,5.345722518403471,False,True,positive_fold_rate;worst_fold_floor
15,240,flow_reversal,range_bps,0.98,14,214,-4993.297151647348,-399.4637721317877,0.5714285714285714,-253.01957979392412,3.3923000569399346,False,True,positive_fold_rate;positive_total_account_return;worst_fold_floor
120,240,reversal,range_bps,0.8,14,335,-2760.3179747987656,-220.82543798390125,0.5714285714285714,-258.4135570716604,1.285152905116292,False,True,positive_fold_rate;positive_total_account_return;worst_fold_floor
240,240,reversal,abs_flow_imbalance,0.98,12,69,275.4346313995346,22.034770511962755,0.5,-18.863182919408835,-1.846862331182204,False,True,positive_fold_rate;median_fold_floor
60,120,reversal,range_bps,0.98,14,152,1509.262404417182,120.74099235337454,0.5,-26.864367789008856,0.11866380957648473,False,True,positive_fold_rate
60,120,reversal,range_bps,0.94,14,297,-927.9423142649597,-74.23538514119677,0.5,-33.0204464051604,-0.8801034470828084,False,True,positive_fold_rate;positive_total_account_return;median_fold_floor
60,120,reversal,range_bps,0.9,14,415,110.58017939961186,8.846414351968939,0.5,-35.36297192662944,0.1066560122914606,False,True,positive_fold_rate

## Interpretation

V81 checks whether any fixed BTCUSDC aggTrade-flow family remains stable across the 2026 YTD rolling validation folds. It groups candidates by lookback, horizon, direction, filter feature, and quantile, then evaluates only validation-window outcomes. This is an oracle-style viability screen, not a deployment selector. If no family passes here, this feature family does not justify another threshold-tuning loop.

The result does not promote a strategy route. The best family still misses the required stability floor, so the next research step should be a genuinely different hypothesis or a stronger data source, not another selection rule over the same candidate family.
