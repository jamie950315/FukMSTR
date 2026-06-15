# Research V192 BTCUSDC Long-Base Low-ProbZ Throttle

## Decision

- Status: `long_base_low_probz_throttle_candidate_ready`
- Promote to live: `False`
- Selected policy: `v192_long_base_low_probz7_le2p339038_throttle0p50`
- Low-probZ throttle passed: `True`
- Return delta vs V191: `13.382016170620318` pct
- Return improvement rate vs V191: `0.0034158692312399063`
- Drawdown improvement vs V191: `0.0` pct
- Holdout return delta vs V191: `7.527609978169721` pct
- Holdout drawdown improvement vs V191: `7.105427357601002e-15` pct
- Throttle trades: `37`
- Throttle active months: `13`
- Throttle max-month share: `16.216216216216218` pct
- Throttle max single-trade delta share: `18.21197152696949` pct
- Message: V192 reduces exposure in an independent long-base low-probability-z bucket and avoids modifying rows already changed by V188 through V191.

## Iteration Metrics

| Metric | V191 | V192 |
|---|---:|---:|
| Account return estimate | 3917.60% | 3930.98% |
| Improvement | - | +13.38 percentage points |
| Max drawdown | -30.20% | -30.20% |
| Positive months | 24/24 | 24/24 |
| Holdout return | 1370.24% | 1377.77% |
| Holdout months | 6/6 | 6/6 |

## Overlay Rules

- Base path: V191 selected account path.
- V192 only changes `indicator_key=v125_top7_lb14_coverage`, `side=long`, `leg=base`, `v188_state_action=unchanged`, `v189_state_action=unchanged`, `v190_state_action=unchanged`, `v191_state_action=unchanged` rows.
- Selected probability-z rule: `prob_z_7d <= 2.339038`.
- Selected throttle multiplier: `0.50x` on top of the V191 account return for that existing bucket.
- V192 does not add trades, change trade side, or change existing entry thresholds.
- V192 deliberately avoids rows already modified by V188, V189, V190, or V191.

## Policy Comparison

policy,trade_count,throttle_trade_count,throttle_active_month_count,throttle_max_month_trade_share_pct,throttle_max_single_trade_delta_share_pct,total_account_return_pct,max_drawdown_pct,positive_months,month_count,worst_month_pct,holdout_return_pct,holdout_max_drawdown_pct,holdout_positive_months,holdout_month_count,return_delta_pct,return_improvement_rate,drawdown_improvement_pct,worst_month_improvement_pct,positive_month_delta,holdout_return_delta_pct,holdout_drawdown_improvement_pct,holdout_positive_month_delta,low_probz_throttle_passed,low_probz_throttle_score
v192_long_base_low_probz7_le2p339038_throttle0p50,645,37,13,16.216216216216218,18.21197152696949,3930.9840274639096,-30.199288542202567,24,24,1.1788398237714812,1377.770488779958,-24.29953968336345,6,6,13.382016170620318,0.0034158692312399063,0.0,0.0,0,7.527609978169721,7.105427357601002e-15,0,True,50.001229158173935
v191_baseline_no_long_base_low_probz_throttle,645,0,0,0.0,0.0,3917.6020112932893,-30.199288542202567,24,24,1.1788398237714812,1370.2428788017883,-24.299539683363456,6,6,0.0,0.0,0.0,0.0,0,0.0,0.0,0,False,52.5
v192_long_base_low_probz7_le2p339038_throttle0p75,645,37,13,16.216216216216218,18.211971526969492,3924.293019378599,-30.199288542202567,24,24,1.1788398237714812,1374.006683790873,-24.29953968336345,6,6,6.691008085309932,0.001707934615619895,0.0,0.0,0,3.763804989084747,7.105427357601002e-15,0,False,37.66451358923609

## Selected Monthly Path

month,trade_count,throttle_trade_count,baseline_return_pct,candidate_return_pct,return_delta_pct
2024-07,16,1,6.019989806430463,10.758067865408812,4.738078058978349
2024-08,28,0,41.98085569462484,41.98085569462484,0.0
2024-09,11,0,1.6453003588625263,1.6453003588625263,0.0
2024-10,17,2,1.3535325997491825,1.6488704704987098,0.29533787074952733
2024-11,37,1,245.44994442521642,245.165770926019,-0.28417349919740786
2024-12,29,0,650.152756401587,650.152756401587,0.0
2025-01,21,0,99.19217875858327,99.19217875858327,0.0
2025-02,31,0,188.13855754238594,188.13855754238594,0.0
2025-03,55,0,142.14311208872886,142.14311208872886,0.0
2025-04,25,1,1.5339514309821407,1.5339514309821407,0.0
2025-05,29,0,1.7693511365606376,1.7693511365606376,0.0
2025-06,14,0,1.1788398237714812,1.1788398237714812,0.0
2025-07,23,4,7.116023435288084,6.0027988291094525,-1.1132246061786315
2025-08,19,3,1.54656428525329,1.6091196596098074,0.06255537435651748
2025-09,11,4,1.420537878003299,2.1284625069520398,0.7079246289487409
2025-10,37,0,880.4663447058791,880.4663447058791,0.0
2025-11,46,2,239.256362172215,241.5727738861731,2.3164117139581037
2025-12,21,2,36.994929947378864,36.12642659821496,-0.8685033491639018
2026-01,31,6,8.36851697410966,11.76962499945521,3.4011080253455503
2026-02,54,0,652.7826216047469,652.7826216047469,0.0
2026-03,28,5,83.2901741409876,86.674504302475,3.384330161487398
2026-04,12,0,28.443412986093655,28.443412986093655,0.0
2026-05,18,3,5.900535728335079,5.667252285670481,-0.23328344266459844
2026-06,32,3,591.4576173675152,592.4330726015165,0.9754552340012879

## Selected Action Profile

v192_state_action,v191_state_action,v190_state_action,v189_state_action,v188_state_action,indicator_key,side,leg,trade_count,baseline_return_pct,candidate_return_pct,win_rate_pct,avg_multiplier,avg_prob_z_7d,avg_prob_z_30d,avg_direction_probability,return_delta_pct
long_base_low_probz_throttle,unchanged,unchanged,unchanged,unchanged,v125_top7_lb14_coverage,long,base,37,-26.76403234124187,-13.382016170620934,48.64864864864865,0.5,2.0795503671404716,2.120662094610155,,13.382016170620934
unchanged,long_base_prior_range_stepup,unchanged,unchanged,unchanged,v120_peak,long,base,9,25.141345183888703,25.141345183888703,55.55555555555556,1.0,2.2135388041923045,2.325888855801316,,0.0
unchanged,long_base_prior_range_stepup,unchanged,unchanged,unchanged,v122_drought,long,base,5,72.47622143016301,72.47622143016301,40.0,1.0,1.647389322832105,1.8292948144896066,,0.0
unchanged,long_base_prior_range_stepup,unchanged,unchanged,unchanged,v123_threshold,long,base,5,18.87842098313215,18.87842098313215,80.0,1.0,3.0455787992481307,2.9096576553760336,0.6167938669142636,0.0
unchanged,long_base_prior_range_stepup,unchanged,unchanged,unchanged,v125_top3_lb14_quality,long,base,2,4.510670632487131,4.510670632487131,50.0,1.0,2.873863400924339,3.2738719229084614,,0.0
unchanged,long_base_prior_range_stepup,unchanged,unchanged,unchanged,v125_top5_lb14_strict,long,base,2,1.8942895343326076,1.8942895343326076,50.0,1.0,2.333147308712493,2.35386164317549,,0.0
unchanged,long_base_prior_range_stepup,unchanged,unchanged,unchanged,v125_top7_lb14_coverage,long,base,82,97.88989868976415,97.88989868976415,57.3170731707317,1.0,2.5274638842497996,2.3853867058605442,0.6363864308780771,0.0
unchanged,unchanged,short_base_prior_rally_stepup,unchanged,unchanged,v120_peak,short,base,19,105.51151737251192,105.51151737251192,73.68421052631578,1.0,2.3490789972527453,2.3647473778775594,,0.0
unchanged,unchanged,short_base_prior_rally_stepup,unchanged,unchanged,v122_drought,short,base,11,103.70057242332194,103.70057242332194,72.72727272727273,1.0,1.2462714849401015,1.564187105378647,,0.0
unchanged,unchanged,short_base_prior_rally_stepup,unchanged,unchanged,v123_threshold,short,base,7,11.447572589808894,11.447572589808894,14.285714285714285,1.0,2.979674650791471,2.8707974830422436,0.618377276465652,0.0
unchanged,unchanged,short_base_prior_rally_stepup,unchanged,unchanged,v125_top5_lb14_strict,short,base,14,25.916387423759787,25.916387423759787,57.14285714285714,1.0,2.3488332971506076,2.1206992141495613,,0.0
unchanged,unchanged,short_base_prior_rally_stepup,unchanged,unchanged,v125_top7_lb14_coverage,short,base,22,4.738603526536682,4.738603526536682,13.636363636363635,1.0,2.5139174057449627,2.3061200933623605,,0.0
unchanged,unchanged,unchanged,rescue_mid_range_extreme_stepup,unchanged,rescue_mid_0p62_0p66,long,rescue,20,399.93825355359786,399.93825355359786,80.0,1.0,3.1300467889355286,2.8882004649804633,0.633239015487182,0.0
unchanged,unchanged,unchanged,unchanged,drought_trend_emotion_stepup,v122_drought,long,base,19,1905.6236437704756,1905.6236437704756,89.47368421052632,1.0,2.821359902560159,2.6875130095138444,0.6259027060956084,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,rescue_high_ge_0p66,long,rescue,3,520.3353062334036,520.3353062334036,100.0,1.0,3.403853970306612,3.116809126857413,0.6649528535357555,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,rescue_high_ge_0p66,short,rescue,2,16.146291252263783,16.146291252263783,100.0,1.0,4.003658902005513,4.0025182574182825,0.6610852049607218,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,rescue_low_0p60_0p62,long,rescue,50,374.75329255682277,374.75329255682277,66.0,1.0,2.7238856643205396,2.555634505719085,0.6092548858010531,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,rescue_low_0p60_0p62,short,rescue,12,22.178132733981656,22.178132733981656,75.0,1.0,2.665457780454716,2.484016688164632,0.6089722073316506,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,rescue_mid_0p62_0p66,long,rescue,3,3.683850753652525,3.683850753652525,33.33333333333333,1.0,3.1049458576930946,2.8469838985325566,0.6269437181674801,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,rescue_mid_0p62_0p66,short,rescue,5,9.059042829602994,9.059042829602994,40.0,1.0,3.3533797051313172,3.045057657262811,0.6432533233620299,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,v120_peak,long,base,86,67.28953902425228,67.28953902425228,47.674418604651166,1.0,2.426079564161152,2.370498363869162,0.6128626657354204,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,v122_drought,long,base,49,104.15296094585817,104.15296094585817,59.183673469387756,1.0,2.1883673272896185,2.0952581466842917,0.6202614772240619,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,v123_threshold,long,base,31,50.574560002166535,50.574560002166535,64.51612903225806,1.0,2.9598370393302242,2.869019526908257,0.6120373613432484,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,v123_threshold,short,base,2,0.0,0.0,0.0,1.0,4.181143998169684,3.5370066227068846,0.6207562505261057,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,v125_top3_lb14_quality,long,base,6,2.2451953180658704,2.2451953180658704,50.0,1.0,3.072709339916333,3.0121969707013903,,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,v125_top3_lb14_quality,short,base,2,-6.458624260726035,-6.458624260726035,0.0,1.0,2.8764581869562695,3.3555930167089416,,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,v125_top5_lb14_strict,long,base,35,-10.385269679233303,-10.385269679233303,48.57142857142857,1.0,2.0803508174208547,2.0117505210315847,0.6013895283518357,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,v125_top7_lb14_coverage,long,base,69,2.9946066925528525,2.9946066925528525,55.072463768115945,1.0,2.7642598807722374,2.5137087912874536,0.6093810296187513,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,v125_top7_lb14_coverage,short,base,36,10.12976211808633,10.12976211808633,33.33333333333333,1.0,2.5885972798346626,2.466785616328233,0.6068062824127889,0.0

## Interpretation

V192 treats low 7-day probability z-score as risk context for a remaining long-base coverage bucket. It reduces size only; it is not a new entry or exit signal.

This remains a research audit, not a live trading guarantee.
