# Research V99 BTCUSDC Low-Cost Headroom Results

## Decision

- Evaluated rows: `1620`
- Passing low-cost rows: `3`
- Passing base policies: `2`
- Passing nonzero-fee base policies: `1`
- Selected nonzero-fee base policy: `hgb_h30_p0.45_rq0.00_fq0.50`
- Maximum passing nonzero fee: `0.25` bps
- Zero-fee research policy: `hgb_h30_p0.40_rq0.00_fq0.50`
- Fee scenarios: `[0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0]` bps

## Policy Headroom

base_policy_id,passing_fee_count,max_passing_fee_bps,max_passing_nonzero_fee_bps,zero_fee_only,selected_policy_id_at_max_fee,max_fee_selector_total_net_pnl_bps,max_fee_selector_win_rate,max_fee_holdout_total_net_pnl_bps,max_fee_holdout_win_rate
hgb_h30_p0.45_rq0.00_fq0.50,2,0.25,0.25,False,hgb_h30_p0.45_rq0.00_fq0.50_fee0.25,1018.4862606980778,0.5925925925925926,1330.7744829196695,0.550744248985115
hgb_h30_p0.40_rq0.00_fq0.50,1,0.0,,True,hgb_h30_p0.40_rq0.00_fq0.50_fee0,828.2675763309178,0.5528455284552846,2303.036742862747,0.5607808340727596
hgb_h30_p0.50_rq0.50_fq0.50,0,,,False,,,,,
hgb_h120_p0.50_rq0.50_fq0.00,0,,,False,,,,,
hgb_h120_p0.35_rq0.50_fq0.50,0,,,False,,,,,
hgb_h120_p0.40_rq0.50_fq0.50,0,,,False,,,,,
hgb_h30_p0.50_rq0.00_fq0.50,0,,,False,,,,,
hgb_h60_p0.55_rq0.00_fq0.50,0,,,False,,,,,
hgb_h60_p0.55_rq0.50_fq0.50,0,,,False,,,,,
hgb_h60_p0.55_rq0.75_fq0.50,0,,,False,,,,,
hgb_h120_p0.55_rq0.50_fq0.50,0,,,False,,,,,
hgb_h30_p0.50_rq0.75_fq0.50,0,,,False,,,,,
hgb_h60_p0.50_rq0.75_fq0.50,0,,,False,,,,,
hgb_h30_p0.50_rq0.00_fq0.00,0,,,False,,,,,
hgb_h60_p0.55_rq0.50_fq0.75,0,,,False,,,,,
hgb_h120_p0.45_rq0.50_fq0.50,0,,,False,,,,,
hgb_h60_p0.55_rq0.00_fq0.75,0,,,False,,,,,
hgb_h60_p0.40_rq0.50_fq0.75,0,,,False,,,,,
hgb_h120_p0.50_rq0.00_fq0.50,0,,,False,,,,,
hgb_h30_p0.40_rq0.75_fq0.75,0,,,False,,,,,

## Top Candidate Rows

policy_id,base_policy_id,passed_low_cost_gate,fee_bps,selector_trade_count,selector_avg_trades_per_calendar_day,selector_total_net_pnl_bps,selector_win_rate,holdout_trade_count,holdout_avg_trades_per_calendar_day,holdout_total_net_pnl_bps,holdout_win_rate
hgb_h30_p0.45_rq0.00_fq0.50_fee0.25,hgb_h30_p0.45_rq0.00_fq0.50,True,0.25,216,1.7851239669421488,1018.4862606980778,0.5925925925925926,739,2.019125683060109,1330.7744829196695,0.550744248985115
hgb_h30_p0.40_rq0.00_fq0.50_fee0,hgb_h30_p0.40_rq0.00_fq0.50,True,0.0,369,3.049586776859504,828.2675763309178,0.5528455284552846,1127,3.079234972677596,2303.036742862747,0.5607808340727596
hgb_h30_p0.45_rq0.00_fq0.50_fee0,hgb_h30_p0.45_rq0.00_fq0.50,True,0.0,216,1.7851239669421488,1072.4862606980778,0.5972222222222222,739,2.019125683060109,1515.5244829196695,0.5534506089309879
hgb_h30_p0.50_rq0.50_fq0.50_fee4,hgb_h30_p0.50_rq0.50_fq0.50,False,4.0,90,0.743801652892562,-227.57417894487443,0.43333333333333335,311,0.8497267759562842,2509.389134169969,0.5401929260450161
hgb_h120_p0.50_rq0.50_fq0.00_fee4,hgb_h120_p0.50_rq0.50_fq0.00,False,4.0,130,1.0743801652892562,-1748.348420607257,0.4846153846153846,381,1.040983606557377,2072.8458704270997,0.5433070866141733
hgb_h120_p0.35_rq0.50_fq0.50_fee4,hgb_h120_p0.35_rq0.50_fq0.50,False,4.0,60,0.49586776859504134,830.1466210711097,0.6,186,0.5081967213114754,1733.1338620332717,0.5376344086021505
hgb_h120_p0.40_rq0.50_fq0.50_fee4,hgb_h120_p0.40_rq0.50_fq0.50,False,4.0,60,0.49586776859504134,830.1466210711097,0.6,186,0.5081967213114754,1733.1338620332717,0.5376344086021505
hgb_h30_p0.50_rq0.00_fq0.50_fee4,hgb_h30_p0.50_rq0.00_fq0.50,False,4.0,102,0.8429752066115702,-8.705417729288207,0.49019607843137253,361,0.9863387978142076,1692.5205001048919,0.5373961218836565
hgb_h60_p0.55_rq0.00_fq0.50_fee4,hgb_h60_p0.55_rq0.00_fq0.50,False,4.0,38,0.3140495867768595,-1029.0574033384182,0.39473684210526316,138,0.3770491803278688,1679.239846971347,0.5652173913043478
hgb_h60_p0.55_rq0.50_fq0.50_fee4,hgb_h60_p0.55_rq0.50_fq0.50,False,4.0,32,0.2644628099173554,-572.2675933805228,0.5,117,0.319672131147541,1675.0262867237905,0.5641025641025641
hgb_h60_p0.55_rq0.75_fq0.50_fee4,hgb_h60_p0.55_rq0.75_fq0.50,False,4.0,21,0.17355371900826447,-96.01815632182127,0.5238095238095238,75,0.20491803278688525,1490.312241112302,0.5466666666666666
hgb_h120_p0.55_rq0.50_fq0.50_fee4,hgb_h120_p0.55_rq0.50_fq0.50,False,4.0,34,0.2809917355371901,-440.89107315277545,0.5588235294117647,115,0.31420765027322406,1265.5851629699525,0.5217391304347826

## Passing Candidate Rows

policy_id,base_policy_id,passed_low_cost_gate,fee_bps,selector_trade_count,selector_avg_trades_per_calendar_day,selector_total_net_pnl_bps,selector_win_rate,holdout_trade_count,holdout_avg_trades_per_calendar_day,holdout_total_net_pnl_bps,holdout_win_rate
hgb_h30_p0.45_rq0.00_fq0.50_fee0.25,hgb_h30_p0.45_rq0.00_fq0.50,True,0.25,216,1.7851239669421488,1018.4862606980778,0.5925925925925926,739,2.019125683060109,1330.7744829196695,0.550744248985115
hgb_h30_p0.40_rq0.00_fq0.50_fee0,hgb_h30_p0.40_rq0.00_fq0.50,True,0.0,369,3.049586776859504,828.2675763309178,0.5528455284552846,1127,3.079234972677596,2303.036742862747,0.5607808340727596
hgb_h30_p0.45_rq0.00_fq0.50_fee0,hgb_h30_p0.45_rq0.00_fq0.50,True,0.0,216,1.7851239669421488,1072.4862606980778,0.5972222222222222,739,2.019125683060109,1515.5244829196695,0.5534506089309879

## Interpretation

V99 replays the V97 HGB regime candidate grid with fine-grained low-cost assumptions. It does not retune probability or regime thresholds. This measures execution-cost headroom for the high-frequency research route and is not a live trading guarantee.
