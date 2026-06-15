# Research V193 BTCUSDC Long-Base Top5 Premium6h Throttle

## Decision

- Status: `long_base_top5_premium6h_throttle_candidate_ready`
- Promote to live: `False`
- Selected policy: `v193_long_base_top5_premium6h_ge_neg4p576517_throttle0p00`
- Top5 premium6h throttle passed: `True`
- Return delta vs V192: `19.670988907481387` pct
- Return improvement rate vs V192: `0.005004087722068971`
- Drawdown improvement vs V192: `0.0` pct
- Holdout return delta vs V192: `8.436393627915322` pct
- Holdout drawdown improvement vs V192: `0.0` pct
- Throttle trades: `18`
- Throttle active months: `10`
- Throttle max-month share: `16.666666666666664` pct
- Throttle max single-trade delta share: `15.8310515423418` pct
- Message: V193 removes exposure in an independent top5 long-base premium-6h bucket and avoids modifying rows already changed by V188 through V192.

## Iteration Metrics

| Metric | V192 | V193 |
|---|---:|---:|
| Account return estimate | 3930.98% | 3950.66% |
| Improvement | - | +19.67 percentage points |
| Max drawdown | -30.20% | -30.20% |
| Positive months | 24/24 | 24/24 |
| Holdout return | 1377.77% | 1386.21% |
| Holdout months | 6/6 | 6/6 |

## Overlay Rules

- Base path: V192 selected account path.
- V193 only changes `indicator_key=v125_top5_lb14_strict`, `side=long`, `leg=base`, `v188_state_action=unchanged`, `v189_state_action=unchanged`, `v190_state_action=unchanged`, `v191_state_action=unchanged`, `v192_state_action=unchanged` rows.
- Selected 6-hour premium rule: `premium_close_bps_6h >= -4.576517`.
- Selected throttle multiplier: `0.00x` on top of the V192 account return for that existing bucket.
- V193 does not add trades, change trade side, or change existing entry thresholds.
- V193 deliberately avoids rows already modified by V188, V189, V190, V191, or V192.

## Policy Comparison

policy,trade_count,throttle_trade_count,throttle_active_month_count,throttle_max_month_trade_share_pct,throttle_max_single_trade_delta_share_pct,total_account_return_pct,max_drawdown_pct,positive_months,month_count,worst_month_pct,holdout_return_pct,holdout_max_drawdown_pct,holdout_positive_months,holdout_month_count,return_delta_pct,return_improvement_rate,drawdown_improvement_pct,worst_month_improvement_pct,positive_month_delta,holdout_return_delta_pct,holdout_drawdown_improvement_pct,holdout_positive_month_delta,top5_premium6h_throttle_passed,top5_premium6h_throttle_score
v193_long_base_top5_premium6h_ge_neg4p576517_throttle0p00,645,18,10,16.666666666666664,15.8310515423418,3950.655016371391,-30.199288542202567,24,24,1.1788398237714812,1386.2068824078733,-24.29953968336345,6,6,19.670988907481387,0.005004087722068971,0.0,0.0,0,8.436393627915322,0.0,0,True,59.34338691151681
v193_long_base_top5_premium6h_ge_neg4p576517_throttle0p25,645,18,10,16.666666666666664,15.8310515423418,3945.7372691445207,-30.199288542202567,24,24,1.1788398237714812,1384.0977840008945,-24.29953968336345,6,6,14.753241680611154,0.0037530657915517576,0.0,0.0,0,6.3272952209365485,0.0,0,True,51.261992074178416
v192_baseline_no_long_base_top5_premium6h_throttle,645,0,0,0.0,0.0,3930.9840274639096,-30.199288542202567,24,24,1.1788398237714812,1377.770488779958,-24.29953968336345,6,6,0.0,0.0,0.0,0.0,0,0.0,0.0,0,False,52.5
v193_long_base_top5_premium6h_ge_neg4p576517_throttle0p50,645,18,10,16.666666666666664,15.8310515423418,3940.8195219176505,-30.199288542202567,24,24,1.1788398237714812,1381.9886855939155,-24.299539683363456,6,6,9.835494453740921,0.002502043861034544,0.0,0.0,0,4.218196813957547,-7.105427357601002e-15,0,False,43.18059723683968

## Selected Monthly Path

month,trade_count,throttle_trade_count,baseline_return_pct,candidate_return_pct,return_delta_pct
2024-07,16,3,10.758067865408812,12.603409387375006,1.8453415219661942
2024-08,28,1,41.98085569462484,43.82637543028452,1.8455197356596784
2024-09,11,0,1.6453003588625263,1.6453003588625263,0.0
2024-10,17,2,1.6488704704987098,5.972801513742798,4.323931043244088
2024-11,37,0,245.165770926019,245.165770926019,0.0
2024-12,29,1,650.152756401587,653.8982467324812,3.7454903308941994
2025-01,21,0,99.19217875858327,99.19217875858327,0.0
2025-02,31,1,188.13855754238594,192.7104106415761,4.57185309919015
2025-03,55,0,142.14311208872886,142.14311208872886,0.0
2025-04,25,0,1.5339514309821407,1.5339514309821407,0.0
2025-05,29,0,1.7693511365606376,1.7693511365606376,0.0
2025-06,14,0,1.1788398237714812,1.1788398237714812,0.0
2025-07,23,2,6.002798829109453,3.262517842980795,-2.7402809861286586
2025-08,19,0,1.6091196596098074,1.6091196596098074,0.0
2025-09,11,0,2.1284625069520393,2.1284625069520393,0.0
2025-10,37,1,880.4663447058791,879.90049314975,-0.5658515561291324
2025-11,46,3,241.5727738861731,239.7813659770423,-1.791407909130811
2025-12,21,0,36.12642659821496,36.12642659821496,0.0
2026-01,31,2,11.76962499945521,16.4979730945695,4.728348095114288
2026-02,54,0,652.7826216047469,652.7826216047469,0.0
2026-03,28,0,86.674504302475,86.674504302475,0.0
2026-04,12,0,28.443412986093655,28.443412986093655,0.0
2026-05,18,0,5.667252285670481,5.667252285670481,0.0
2026-06,32,2,592.4330726015165,596.1411181343177,3.7080455328011794

## Selected Action Profile

v193_state_action,v192_state_action,v191_state_action,v190_state_action,v189_state_action,v188_state_action,indicator_key,side,leg,trade_count,baseline_return_pct,candidate_return_pct,win_rate_pct,avg_multiplier,avg_premium_close_bps_6h,avg_prob_z_7d,avg_direction_probability,return_delta_pct
long_base_top5_premium6h_throttle,unchanged,unchanged,unchanged,unchanged,unchanged,v125_top5_lb14_strict,long,base,18,-19.670988907481238,0.0,0.0,0.0,-2.748255555555556,1.9584762375440805,0.6000001709108433,19.670988907481238
unchanged,long_base_low_probz_throttle,unchanged,unchanged,unchanged,unchanged,v125_top7_lb14_coverage,long,base,37,-13.382016170620934,-13.382016170620934,48.64864864864865,1.0,-4.267672972972973,2.0795503671404716,,0.0
unchanged,unchanged,long_base_prior_range_stepup,unchanged,unchanged,unchanged,v120_peak,long,base,9,25.141345183888703,25.141345183888703,55.55555555555556,1.0,-1.3467111111111114,2.2135388041923045,,0.0
unchanged,unchanged,long_base_prior_range_stepup,unchanged,unchanged,unchanged,v122_drought,long,base,5,72.47622143016301,72.47622143016301,40.0,1.0,-2.3691866666666668,1.647389322832105,,0.0
unchanged,unchanged,long_base_prior_range_stepup,unchanged,unchanged,unchanged,v123_threshold,long,base,5,18.87842098313215,18.87842098313215,80.0,1.0,1.984343333333333,3.0455787992481307,0.6167938669142636,0.0
unchanged,unchanged,long_base_prior_range_stepup,unchanged,unchanged,unchanged,v125_top3_lb14_quality,long,base,2,4.510670632487131,4.510670632487131,50.0,1.0,-3.185016666666667,2.873863400924339,,0.0
unchanged,unchanged,long_base_prior_range_stepup,unchanged,unchanged,unchanged,v125_top5_lb14_strict,long,base,2,1.8942895343326076,1.8942895343326076,50.0,1.0,-5.358433333333333,2.333147308712493,,0.0
unchanged,unchanged,long_base_prior_range_stepup,unchanged,unchanged,unchanged,v125_top7_lb14_coverage,long,base,82,97.88989868976415,97.88989868976415,57.3170731707317,1.0,-2.468881300813009,2.5274638842497996,0.6363864308780771,0.0
unchanged,unchanged,unchanged,short_base_prior_rally_stepup,unchanged,unchanged,v120_peak,short,base,19,105.51151737251192,105.51151737251192,73.68421052631578,1.0,-3.8578464912280706,2.3490789972527453,,0.0
unchanged,unchanged,unchanged,short_base_prior_rally_stepup,unchanged,unchanged,v122_drought,short,base,11,103.70057242332194,103.70057242332194,72.72727272727273,1.0,-3.7226954545454545,1.2462714849401015,,0.0
unchanged,unchanged,unchanged,short_base_prior_rally_stepup,unchanged,unchanged,v123_threshold,short,base,7,11.447572589808894,11.447572589808894,14.285714285714285,1.0,-2.49835,2.979674650791471,0.618377276465652,0.0
unchanged,unchanged,unchanged,short_base_prior_rally_stepup,unchanged,unchanged,v125_top5_lb14_strict,short,base,14,25.916387423759787,25.916387423759787,57.14285714285714,1.0,-4.244359523809524,2.3488332971506076,,0.0
unchanged,unchanged,unchanged,short_base_prior_rally_stepup,unchanged,unchanged,v125_top7_lb14_coverage,short,base,22,4.738603526536682,4.738603526536682,13.636363636363635,1.0,-3.1809136363636368,2.5139174057449627,,0.0
unchanged,unchanged,unchanged,unchanged,rescue_mid_range_extreme_stepup,unchanged,rescue_mid_0p62_0p66,long,rescue,20,399.93825355359786,399.93825355359786,80.0,1.0,-4.12528,3.1300467889355286,0.633239015487182,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,drought_trend_emotion_stepup,v122_drought,long,base,19,1905.6236437704756,1905.6236437704756,89.47368421052632,1.0,-0.03366052631578988,2.821359902560159,0.6259027060956084,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,rescue_high_ge_0p66,long,rescue,3,520.3353062334036,520.3353062334036,100.0,1.0,-4.109183333333333,3.403853970306612,0.6649528535357555,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,rescue_high_ge_0p66,short,rescue,2,16.146291252263783,16.146291252263783,100.0,1.0,-4.420166666666667,4.003658902005513,0.6610852049607218,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,rescue_low_0p60_0p62,long,rescue,50,374.75329255682277,374.75329255682277,66.0,1.0,-4.391783666666667,2.7238856643205396,0.6092548858010531,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,rescue_low_0p60_0p62,short,rescue,12,22.178132733981656,22.178132733981656,75.0,1.0,-4.159605555555555,2.665457780454716,0.6089722073316506,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,rescue_mid_0p62_0p66,long,rescue,3,3.683850753652525,3.683850753652525,33.33333333333333,1.0,-3.7327611111111114,3.1049458576930946,0.6269437181674801,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,rescue_mid_0p62_0p66,short,rescue,5,9.059042829602994,9.059042829602994,40.0,1.0,-4.5288466666666665,3.3533797051313172,0.6432533233620299,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,v120_peak,long,base,86,67.28953902425228,67.28953902425228,47.674418604651166,1.0,-3.348912209302326,2.426079564161152,0.6128626657354204,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,v122_drought,long,base,49,104.15296094585817,104.15296094585817,59.183673469387756,1.0,-3.0679197278911565,2.1883673272896185,0.6202614772240619,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,v123_threshold,long,base,31,50.574560002166535,50.574560002166535,64.51612903225806,1.0,-2.0930817204301078,2.9598370393302242,0.6120373613432484,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,v123_threshold,short,base,2,0.0,0.0,0.0,1.0,-4.042916666666667,4.181143998169684,0.6207562505261057,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,v125_top3_lb14_quality,long,base,6,2.2451953180658704,2.2451953180658704,50.0,1.0,-3.612377777777778,3.072709339916333,,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,v125_top3_lb14_quality,short,base,2,-6.458624260726035,-6.458624260726035,0.0,1.0,-4.2743,2.8764581869562695,,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,v125_top5_lb14_strict,long,base,17,9.285719228247935,9.285719228247935,52.94117647058824,1.0,-5.192930392156863,2.2093944902315563,0.602778885792828,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,v125_top7_lb14_coverage,long,base,69,2.9946066925528525,2.9946066925528525,55.072463768115945,1.0,-4.042581884057971,2.7642598807722374,0.6093810296187513,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,v125_top7_lb14_coverage,short,base,36,10.12976211808633,10.12976211808633,33.33333333333333,1.0,-3.397428240740741,2.5885972798346626,0.6068062824127889,0.0

## Interpretation

V193 treats insufficiently negative 6-hour premium as a risk context for a remaining top5 long-base bucket. It removes size only; it is not a new entry or exit signal.

This remains a research audit, not a live trading guarantee.
