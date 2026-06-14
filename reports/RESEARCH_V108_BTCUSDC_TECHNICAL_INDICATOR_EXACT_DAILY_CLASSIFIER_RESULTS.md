# Research V108 BTCUSDC Technical Indicator Exact Daily Classifier Results

## Decision

- Evaluated candidates: `100`
- Passing exact-daily candidates: `3`
- Selector-locked selected candidate: `hgb_technical_exact_daily_top5_h30_p0.000000`
- Holdout passed after selector lock: `False`
- Goal satisfied by strict exact-daily selection: `False`
- Technical features added: `18`

## Selected Candidate

policy_id,passed_exact_daily_gate,horizon_minutes,daily_top_k,probability_floor,feature_count,selector_trade_count,selector_active_day_count,selector_calendar_day_count,selector_avg_trades_per_calendar_day,selector_total_net_pnl_bps,selector_win_rate,selector_max_drawdown_bps,selector_calendar_positive_month_rate,holdout_trade_count,holdout_active_day_count,holdout_calendar_day_count,holdout_avg_trades_per_calendar_day,holdout_total_net_pnl_bps,holdout_win_rate,holdout_max_drawdown_bps,holdout_calendar_positive_month_rate
hgb_technical_exact_daily_top5_h30_p0.000000,False,30,5,0.0,67,602,121,121,4.975206611570248,3160.728147701455,0.5598006644518272,470.11834869042514,1.0,1827,366,366,4.991803278688525,5361.629649126495,0.5298303229337712,839.7896446974406,0.8461538461538461

## V106 Comparison

- V106 policy: `hgb_ma_exact_daily_top4_h30_p0.000000`
- V108 policy: `hgb_technical_exact_daily_top5_h30_p0.000000`
- Selector PnL delta: `-511.354196` bps
- Selector win-rate delta: `0.000549`
- Holdout PnL delta: `-1418.184612` bps
- Holdout win-rate delta: `-0.033781`
- Holdout max-drawdown delta: `54.082709` bps

## Top Candidates

policy_id,passed_exact_daily_gate,horizon_minutes,daily_top_k,probability_floor,feature_count,selector_trade_count,selector_active_day_count,selector_calendar_day_count,selector_avg_trades_per_calendar_day,selector_total_net_pnl_bps,selector_win_rate,selector_max_drawdown_bps,selector_calendar_positive_month_rate,holdout_trade_count,holdout_active_day_count,holdout_calendar_day_count,holdout_avg_trades_per_calendar_day,holdout_total_net_pnl_bps,holdout_win_rate,holdout_max_drawdown_bps,holdout_calendar_positive_month_rate
hgb_technical_exact_daily_top2_h30_p0.000000,True,30,2,0.0,67,242,121,121,2.0,1222.7494520733708,0.5785123966942148,666.1775718613512,1.0,732,366,366,2.0,4098.967606089306,0.5642076502732241,389.3368380902782,0.6923076923076923
hgb_technical_exact_daily_top1_h30_p0.000000,True,30,1,0.0,67,121,121,121,1.0,1085.4029770293882,0.5950413223140496,325.53133328213875,1.0,366,366,366,1.0,3215.645958711206,0.5901639344262295,703.0838069258972,0.7692307692307693
hgb_technical_exact_daily_top1_h5_p0.000000,True,5,1,0.0,67,121,121,121,1.0,815.8558891070011,0.6033057851239669,135.0092853585223,0.8,366,366,366,1.0,2711.1286501413006,0.5792349726775956,280.66854116118725,0.7692307692307693
hgb_technical_exact_daily_top5_h30_p0.400000,False,30,5,0.4,67,561,119,121,4.636363636363637,3206.550062449625,0.5632798573975044,470.11834869042514,1.0,1679,354,366,4.587431693989071,6361.30094555094,0.547945205479452,664.9038832639282,0.8461538461538461
hgb_technical_exact_daily_top5_h30_p0.000000,False,30,5,0.0,67,602,121,121,4.975206611570248,3160.728147701455,0.5598006644518272,470.11834869042514,1.0,1827,366,366,4.991803278688525,5361.629649126495,0.5298303229337712,839.7896446974406,0.8461538461538461
hgb_technical_exact_daily_top5_h30_p0.333333,False,30,5,0.3333333333333333,67,598,121,121,4.9421487603305785,3139.3777397351696,0.5585284280936454,470.11834869042514,1.0,1779,365,366,4.860655737704918,5668.147486787302,0.5368184373243395,761.4938470149945,0.8461538461538461
hgb_technical_exact_daily_top5_h30_p0.350000,False,30,5,0.35,67,592,121,121,4.892561983471074,3137.190172794875,0.5574324324324325,470.11834869042514,1.0,1760,364,366,4.808743169398907,5948.09314506517,0.5392045454545454,767.5239981636181,0.8461538461538461
hgb_technical_exact_daily_top5_h30_p0.340000,False,30,5,0.34,67,596,121,121,4.925619834710743,3130.867955341754,0.5570469798657718,470.11834869042514,1.0,1771,364,366,4.83879781420765,5895.527193195965,0.5381140598531903,761.4938470149938,0.8461538461538461
hgb_technical_exact_daily_top4_h30_p0.400000,False,30,4,0.4,67,454,119,121,3.7520661157024793,2934.66627416924,0.5638766519823789,477.121631019127,1.0,1356,354,366,3.7049180327868854,6263.093828431376,0.5523598820058997,576.2875381854326,0.8461538461538461
hgb_technical_exact_daily_top4_h30_p0.000000,False,30,4,0.0,67,482,121,121,3.9834710743801653,2893.364727832736,0.558091286307054,477.121631019127,1.0,1462,366,366,3.9945355191256833,5471.920985002311,0.5369357045143639,597.3291353928378,0.8461538461538461
hgb_technical_exact_daily_top4_h30_p0.350000,False,30,4,0.35,67,477,121,121,3.9421487603305785,2874.1590143304447,0.5576519916142557,477.121631019127,1.0,1419,364,366,3.877049180327869,5872.399394616551,0.5433403805496829,576.287538185433,0.8461538461538461
hgb_technical_exact_daily_top4_h30_p0.333333,False,30,4,0.3333333333333333,67,481,121,121,3.975206611570248,2868.758473255254,0.5571725571725572,477.121631019127,1.0,1433,365,366,3.9153005464480874,5623.285138311412,0.5408234473133287,576.287538185433,0.8461538461538461

## Passing Candidates

policy_id,passed_exact_daily_gate,horizon_minutes,daily_top_k,probability_floor,feature_count,selector_trade_count,selector_active_day_count,selector_calendar_day_count,selector_avg_trades_per_calendar_day,selector_total_net_pnl_bps,selector_win_rate,selector_max_drawdown_bps,selector_calendar_positive_month_rate,holdout_trade_count,holdout_active_day_count,holdout_calendar_day_count,holdout_avg_trades_per_calendar_day,holdout_total_net_pnl_bps,holdout_win_rate,holdout_max_drawdown_bps,holdout_calendar_positive_month_rate
hgb_technical_exact_daily_top2_h30_p0.000000,True,30,2,0.0,67,242,121,121,2.0,1222.7494520733708,0.5785123966942148,666.1775718613512,1.0,732,366,366,2.0,4098.967606089306,0.5642076502732241,389.3368380902782,0.6923076923076923
hgb_technical_exact_daily_top1_h30_p0.000000,True,30,1,0.0,67,121,121,121,1.0,1085.4029770293882,0.5950413223140496,325.53133328213875,1.0,366,366,366,1.0,3215.645958711206,0.5901639344262295,703.0838069258972,0.7692307692307693
hgb_technical_exact_daily_top1_h5_p0.000000,True,5,1,0.0,67,121,121,121,1.0,815.8558891070011,0.6033057851239669,135.0092853585223,0.8,366,366,366,1.0,2711.1286501413006,0.5792349726775956,280.66854116118725,0.7692307692307693

## Interpretation

V108 adds prior-bar RSI, MACD, Bollinger, ATR, and stochastic-style features to the V106 exact-daily classifier. All new indicators use prior bars only. This remains a research candidate, not a live trading guarantee.
