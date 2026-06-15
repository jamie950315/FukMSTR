# Research V194 BTCUSDC Long-Rescue Premium Discount Stepup

## Decision

- Status: `long_rescue_premium_discount_stepup_candidate_ready`
- Promote to live: `False`
- Selected policy: `v194_long_rescue_premium_open_le_neg0p000351_stepup1p25`
- Premium discount stepup passed: `True`
- Return delta vs V193: `94.04341888980343` pct
- Return improvement rate vs V193: `0.023804513049124877`
- Drawdown improvement vs V193: `0.0` pct
- Holdout return delta vs V193: `66.59777672153336` pct
- Holdout drawdown improvement vs V193: `0.0` pct
- Stepup trades: `37`
- Stepup active months: `9`
- Stepup max-month share: `29.72972972972973` pct
- Stepup max single-trade delta share: `33.6977118349542` pct
- Message: V194 increases size in an independent long-rescue premium-discount bucket and avoids modifying rows already changed by V188 through V193.

## Iteration Metrics

| Metric | V193 | V194 |
|---|---:|---:|
| Account return estimate | 3950.66% | 4044.70% |
| Improvement | - | +94.04 percentage points |
| Max drawdown | -30.20% | -30.20% |
| Positive months | 24/24 | 24/24 |
| Holdout return | 1386.21% | 1452.80% |
| Holdout months | 6/6 | 6/6 |

## Overlay Rules

- Base path: V193 selected account path.
- V194 only changes `side=long`, `leg=rescue`, `v188_state_action=unchanged`, `v189_state_action=unchanged`, `v190_state_action=unchanged`, `v191_state_action=unchanged`, `v192_state_action=unchanged`, `v193_state_action=unchanged` rows.
- Selected premium-open rule: `premium_open <= -0.000351`.
- Selected step-up multiplier: `1.25x` on top of the V193 account return for that existing bucket.
- V194 does not add trades, change trade side, or change existing entry thresholds.
- V194 deliberately avoids rows already modified by V188, V189, V190, V191, V192, or V193.

## Policy Comparison

policy,trade_count,stepup_trade_count,stepup_active_month_count,stepup_max_month_trade_share_pct,stepup_max_single_trade_delta_share_pct,total_account_return_pct,max_drawdown_pct,positive_months,month_count,worst_month_pct,holdout_return_pct,holdout_max_drawdown_pct,holdout_positive_months,holdout_month_count,return_delta_pct,return_improvement_rate,drawdown_improvement_pct,worst_month_improvement_pct,positive_month_delta,holdout_return_delta_pct,holdout_drawdown_improvement_pct,holdout_positive_month_delta,premium_discount_stepup_passed,premium_discount_stepup_score
v194_long_rescue_premium_open_le_neg0p000351_stepup1p25,645,37,9,29.72972972972973,33.6977118349542,4044.6984352611944,-30.199288542202567,24,24,1.1788398237714812,1452.8046591294067,-24.29953968336345,6,6,94.04341888980343,0.023804513049124877,0.0,0.0,0,66.59777672153336,0.0,0,True,198.01149832489665
v194_long_rescue_premium_open_le_neg0p000351_stepup1p15,645,37,9,29.72972972972973,33.69771183495423,4007.081067705273,-30.199288542202567,24,24,1.1788398237714812,1426.1655484407934,-24.29953968336345,6,6,56.42605133388224,0.014282707829474973,0.0,0.0,0,39.958666032920064,0.0,0,True,120.43546473605551
v193_baseline_no_long_rescue_premium_discount_stepup,645,0,0,0.0,0.0,3950.655016371391,-30.199288542202567,24,24,1.1788398237714812,1386.2068824078733,-24.29953968336345,6,6,0.0,0.0,0.0,0.0,0,0.0,0.0,0,False,52.5

## Selected Monthly Path

month,trade_count,stepup_trade_count,baseline_return_pct,candidate_return_pct,return_delta_pct
2024-07,16,0,12.603409387375006,12.603409387375006,0.0
2024-08,28,0,43.82637543028452,43.82637543028452,0.0
2024-09,11,0,1.6453003588625263,1.6453003588625263,0.0
2024-10,17,0,5.972801513742798,5.972801513742798,0.0
2024-11,37,0,245.165770926019,245.165770926019,0.0
2024-12,29,0,653.8982467324812,653.8982467324812,0.0
2025-01,21,0,99.19217875858327,99.19217875858327,0.0
2025-02,31,0,192.7104106415761,192.7104106415761,0.0
2025-03,55,11,142.14311208872886,158.3504797144687,16.207367625739835
2025-04,25,2,1.5339514309821407,3.66390577100206,2.1299543400199195
2025-05,29,2,1.7693511365606376,2.5427658915573397,0.7734147549967021
2025-06,14,0,1.1788398237714812,1.1788398237714812,0.0
2025-07,23,0,3.262517842980795,3.262517842980795,0.0
2025-08,19,0,1.6091196596098074,1.6091196596098074,0.0
2025-09,11,0,2.1284625069520393,2.1284625069520393,0.0
2025-10,37,1,879.90049314975,880.8457721952743,0.9452790455243303
2025-11,46,0,239.7813659770423,239.7813659770423,0.0
2025-12,21,4,36.12642659821496,43.516053000204195,7.389626401989233
2026-01,31,2,16.4979730945695,17.079582574922032,0.5816094803525331
2026-02,54,11,652.7826216047469,711.4953256603237,58.712704055576864
2026-03,28,1,86.674504302475,87.81556526929276,1.1410609668177614
2026-04,12,0,28.443412986093655,28.443412986093655,0.0
2026-05,18,0,5.667252285670481,5.667252285670481,0.0
2026-06,32,3,596.1411181343177,602.3035203531041,6.162402218786383

## Selected Action Profile

v194_state_action,v193_state_action,v192_state_action,v191_state_action,v190_state_action,v189_state_action,v188_state_action,indicator_key,side,leg,trade_count,baseline_return_pct,candidate_return_pct,win_rate_pct,avg_multiplier,avg_premium_open,avg_premium_close_bps_6h,avg_prob_z_7d,avg_direction_probability,return_delta_pct
long_rescue_premium_discount_stepup,unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,rescue_high_ge_0p66,long,rescue,2,11.658384900603291,14.572981125754115,100.0,1.25,-0.000671725,-4.845125,2.9863374692150897,0.6651916253540623,2.9145962251508237
long_rescue_premium_discount_stepup,unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,rescue_low_0p60_0p62,long,rescue,33,353.09192913010315,441.36491141262894,75.75757575757575,1.25,-0.0005231257575757576,-4.669127272727273,2.653811415805591,0.6094168485890377,88.27298228252579
long_rescue_premium_discount_stepup,unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,rescue_mid_0p62_0p66,long,rescue,2,11.42336152850724,14.279201910634049,50.0,1.25,-0.0006389200000000001,-4.280491666666666,3.0838256767750973,0.6217951375008927,2.855840382126809
unchanged,long_base_top5_premium6h_throttle,unchanged,unchanged,unchanged,unchanged,unchanged,v125_top5_lb14_strict,long,base,18,0.0,0.0,0.0,1.0,-0.0003066661111111111,-2.748255555555556,1.9584762375440805,0.6000001709108433,0.0
unchanged,unchanged,long_base_low_probz_throttle,unchanged,unchanged,unchanged,unchanged,v125_top7_lb14_coverage,long,base,37,-13.382016170620934,-13.382016170620934,48.64864864864865,1.0,-0.0004213435135135135,-4.267672972972973,2.0795503671404716,,0.0
unchanged,unchanged,unchanged,long_base_prior_range_stepup,unchanged,unchanged,unchanged,v120_peak,long,base,9,25.141345183888703,25.141345183888703,55.55555555555556,1.0,-0.0001847266666666667,-1.3467111111111114,2.2135388041923045,,0.0
unchanged,unchanged,unchanged,long_base_prior_range_stepup,unchanged,unchanged,unchanged,v122_drought,long,base,5,72.47622143016301,72.47622143016301,40.0,1.0,-0.000190404,-2.3691866666666668,1.647389322832105,,0.0
unchanged,unchanged,unchanged,long_base_prior_range_stepup,unchanged,unchanged,unchanged,v123_threshold,long,base,5,18.87842098313215,18.87842098313215,80.0,1.0,0.00012414000000000001,1.984343333333333,3.0455787992481307,0.6167938669142636,0.0
unchanged,unchanged,unchanged,long_base_prior_range_stepup,unchanged,unchanged,unchanged,v125_top3_lb14_quality,long,base,2,4.510670632487131,4.510670632487131,50.0,1.0,-0.000452245,-3.185016666666667,2.873863400924339,,0.0
unchanged,unchanged,unchanged,long_base_prior_range_stepup,unchanged,unchanged,unchanged,v125_top5_lb14_strict,long,base,2,1.8942895343326076,1.8942895343326076,50.0,1.0,-0.000554945,-5.358433333333333,2.333147308712493,,0.0
unchanged,unchanged,unchanged,long_base_prior_range_stepup,unchanged,unchanged,unchanged,v125_top7_lb14_coverage,long,base,82,97.88989868976415,97.88989868976415,57.3170731707317,1.0,-0.00024113219512195122,-2.468881300813009,2.5274638842497996,0.6363864308780771,0.0
unchanged,unchanged,unchanged,unchanged,short_base_prior_rally_stepup,unchanged,unchanged,v120_peak,short,base,19,105.51151737251192,105.51151737251192,73.68421052631578,1.0,-0.00032018263157894736,-3.8578464912280706,2.3490789972527453,,0.0
unchanged,unchanged,unchanged,unchanged,short_base_prior_rally_stepup,unchanged,unchanged,v122_drought,short,base,11,103.70057242332194,103.70057242332194,72.72727272727273,1.0,-0.00038431545454545453,-3.7226954545454545,1.2462714849401015,,0.0
unchanged,unchanged,unchanged,unchanged,short_base_prior_rally_stepup,unchanged,unchanged,v123_threshold,short,base,7,11.447572589808894,11.447572589808894,14.285714285714285,1.0,-0.00013859428571428572,-2.49835,2.979674650791471,0.618377276465652,0.0
unchanged,unchanged,unchanged,unchanged,short_base_prior_rally_stepup,unchanged,unchanged,v125_top5_lb14_strict,short,base,14,25.916387423759787,25.916387423759787,57.14285714285714,1.0,-0.0003721278571428571,-4.244359523809524,2.3488332971506076,,0.0
unchanged,unchanged,unchanged,unchanged,short_base_prior_rally_stepup,unchanged,unchanged,v125_top7_lb14_coverage,short,base,22,4.738603526536682,4.738603526536682,13.636363636363635,1.0,-0.00032701999999999997,-3.1809136363636368,2.5139174057449627,,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,rescue_mid_range_extreme_stepup,unchanged,rescue_mid_0p62_0p66,long,rescue,20,399.93825355359786,399.93825355359786,80.0,1.0,-0.000409068,-4.12528,3.1300467889355286,0.633239015487182,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,drought_trend_emotion_stepup,v122_drought,long,base,19,1905.6236437704756,1905.6236437704756,89.47368421052632,1.0,-0.00010053947368421052,-0.03366052631578988,2.821359902560159,0.6259027060956084,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,rescue_high_ge_0p66,long,rescue,1,508.6769213328003,508.6769213328003,100.0,1.0,-0.00031549,-2.6373,4.238886972489657,0.6644753098991422,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,rescue_high_ge_0p66,short,rescue,2,16.146291252263783,16.146291252263783,100.0,1.0,-0.00022428999999999998,-4.420166666666667,4.003658902005513,0.6610852049607218,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,rescue_low_0p60_0p62,long,rescue,17,21.661363426719607,21.661363426719607,47.05882352941176,1.0,-0.0002524105882352941,-3.853410784313726,2.8599121467319097,0.608940487447907,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,rescue_low_0p60_0p62,short,rescue,12,22.178132733981656,22.178132733981656,75.0,1.0,-0.0002299125,-4.159605555555555,2.665457780454716,0.6089722073316506,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,rescue_mid_0p62_0p66,long,rescue,1,-7.739510774854713,-7.739510774854713,0.0,1.0,-0.00031549,-2.6373,3.1471862195290896,0.6372408795006551,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,rescue_mid_0p62_0p66,short,rescue,5,9.059042829602994,9.059042829602994,40.0,1.0,-0.0005422760000000001,-4.5288466666666665,3.3533797051313172,0.6432533233620299,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,v120_peak,long,base,86,67.28953902425228,67.28953902425228,47.674418604651166,1.0,-0.0003368820930232558,-3.348912209302326,2.426079564161152,0.6128626657354204,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,v122_drought,long,base,49,104.15296094585817,104.15296094585817,59.183673469387756,1.0,-0.00028851469387755103,-3.0679197278911565,2.1883673272896185,0.6202614772240619,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,v123_threshold,long,base,31,50.574560002166535,50.574560002166535,64.51612903225806,1.0,-0.0002162551612903226,-2.0930817204301078,2.9598370393302242,0.6120373613432484,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,v123_threshold,short,base,2,0.0,0.0,0.0,1.0,-0.00045889,-4.042916666666667,4.181143998169684,0.6207562505261057,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,v125_top3_lb14_quality,long,base,6,2.2451953180658704,2.2451953180658704,50.0,1.0,-0.00032995,-3.612377777777778,3.072709339916333,,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,v125_top3_lb14_quality,short,base,2,-6.458624260726035,-6.458624260726035,0.0,1.0,-0.00013862000000000002,-4.2743,2.8764581869562695,,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,v125_top5_lb14_strict,long,base,17,9.285719228247935,9.285719228247935,52.94117647058824,1.0,-0.0005057688235294117,-5.192930392156863,2.2093944902315563,0.602778885792828,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,v125_top7_lb14_coverage,long,base,69,2.9946066925528525,2.9946066925528525,55.072463768115945,1.0,-0.00041284594202898553,-4.042581884057971,2.7642598807722374,0.6093810296187513,0.0
unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,unchanged,v125_top7_lb14_coverage,short,base,36,10.12976211808633,10.12976211808633,33.33333333333333,1.0,-0.0003583227777777778,-3.397428240740741,2.5885972798346626,0.6068062824127889,0.0

## Interpretation

V194 treats a negative premium open as supportive context for remaining long-rescue trades. It increases size only; it is not a new entry or exit signal.

This remains a research audit, not a live trading guarantee.
