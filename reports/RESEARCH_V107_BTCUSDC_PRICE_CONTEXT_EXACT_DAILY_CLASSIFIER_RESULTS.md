# Research V107 BTCUSDC Price Context Exact Daily Classifier Results

## Decision

- Evaluated candidates: `100`
- Passing exact-daily candidates: `3`
- Selector-locked selected candidate: `hgb_price_context_exact_daily_top5_h30_p0.000000`
- Holdout passed after selector lock: `True`
- Goal satisfied by strict exact-daily selection: `True`
- Price-context features added: `29`

## Selected Candidate

policy_id,passed_exact_daily_gate,horizon_minutes,daily_top_k,probability_floor,feature_count,selector_trade_count,selector_active_day_count,selector_calendar_day_count,selector_avg_trades_per_calendar_day,selector_total_net_pnl_bps,selector_win_rate,selector_max_drawdown_bps,selector_calendar_positive_month_rate,holdout_trade_count,holdout_active_day_count,holdout_calendar_day_count,holdout_avg_trades_per_calendar_day,holdout_total_net_pnl_bps,holdout_win_rate,holdout_max_drawdown_bps,holdout_calendar_positive_month_rate
hgb_price_context_exact_daily_top5_h30_p0.000000,True,30,5,0.0,78,602,121,121,4.975206611570248,2623.5797323484658,0.5863787375415282,821.5103085304067,1.0,1827,366,366,4.991803278688525,6208.386342118734,0.5500821018062397,734.4338897606749,0.7692307692307693

## V106 Comparison

- V106 policy: `hgb_ma_exact_daily_top4_h30_p0.000000`
- V107 policy: `hgb_price_context_exact_daily_top5_h30_p0.000000`
- Selector PnL delta: `-1048.502611` bps
- Selector win-rate delta: `0.027127`
- Holdout PnL delta: `-571.427919` bps
- Holdout win-rate delta: `-0.013529`
- Holdout max-drawdown delta: `-51.273046` bps

## Top Candidates

policy_id,passed_exact_daily_gate,horizon_minutes,daily_top_k,probability_floor,feature_count,selector_trade_count,selector_active_day_count,selector_calendar_day_count,selector_avg_trades_per_calendar_day,selector_total_net_pnl_bps,selector_win_rate,selector_max_drawdown_bps,selector_calendar_positive_month_rate,holdout_trade_count,holdout_active_day_count,holdout_calendar_day_count,holdout_avg_trades_per_calendar_day,holdout_total_net_pnl_bps,holdout_win_rate,holdout_max_drawdown_bps,holdout_calendar_positive_month_rate
hgb_price_context_exact_daily_top5_h30_p0.000000,True,30,5,0.0,78,602,121,121,4.975206611570248,2623.5797323484658,0.5863787375415282,821.5103085304067,1.0,1827,366,366,4.991803278688525,6208.386342118734,0.5500821018062397,734.4338897606749,0.7692307692307693
hgb_price_context_exact_daily_top2_h30_p0.000000,True,30,2,0.0,78,242,121,121,2.0,1064.4193121412661,0.6074380165289256,589.3653545272035,0.8,732,366,366,2.0,4097.325367542093,0.5532786885245902,629.4762493222556,0.9230769230769231
hgb_price_context_exact_daily_top1_h30_p0.000000,True,30,1,0.0,78,121,121,121,1.0,488.7429868781322,0.6363636363636364,367.80180896583494,0.6,366,366,366,1.0,3939.1315703056002,0.5846994535519126,388.08668770208806,0.9230769230769231
hgb_price_context_exact_daily_top5_h30_p0.350000,False,30,5,0.35,78,592,120,121,4.892561983471074,2676.8299415528904,0.5912162162162162,821.5103085304067,1.0,1756,365,366,4.797814207650274,6775.035990608916,0.5609339407744874,738.3407416736791,0.7692307692307693
hgb_price_context_exact_daily_top5_h30_p0.333333,False,30,5,0.3333333333333333,78,599,121,121,4.950413223140496,2635.989126528927,0.5893155258764607,821.5103085304067,1.0,1781,365,366,4.866120218579235,6470.567043644604,0.5569904548006738,742.2841486397729,0.7692307692307693
hgb_price_context_exact_daily_top5_h30_p0.340000,False,30,5,0.34,78,598,121,121,4.9421487603305785,2631.2693325671576,0.5886287625418061,821.5103085304067,1.0,1772,365,366,4.841530054644808,6714.929633131356,0.5586907449209932,742.2841486397729,0.7692307692307693
hgb_price_context_exact_daily_top5_h30_p0.400000,False,30,5,0.4,78,565,118,121,4.669421487603306,2608.593862289163,0.5911504424778761,821.5103085304067,1.0,1677,352,366,4.581967213114754,7110.913178929624,0.56768038163387,715.8150890521674,0.7692307692307693
hgb_price_context_exact_daily_top4_h30_p0.350000,False,30,4,0.35,78,476,120,121,3.9338842975206614,1882.911647220858,0.5987394957983193,732.9988734493238,1.0,1415,365,366,3.866120218579235,6093.271079093569,0.5547703180212014,976.5158013938053,0.8461538461538461
hgb_price_context_exact_daily_top4_h30_p0.333333,False,30,4,0.3333333333333333,78,480,121,121,3.9669421487603307,1855.1556989351707,0.5958333333333333,732.9988734493238,1.0,1434,365,366,3.918032786885246,5829.758606694406,0.5516039051603905,980.4592083598991,0.8461538461538461
hgb_price_context_exact_daily_top4_h30_p0.340000,False,30,4,0.34,78,479,121,121,3.958677685950413,1850.4359049734012,0.5949895615866388,732.9988734493238,1.0,1428,365,366,3.901639344262295,6034.335366106687,0.5525210084033614,980.4592083598991,0.8461538461538461
hgb_price_context_exact_daily_top4_h30_p0.000000,False,30,4,0.0,78,482,121,121,3.9834710743801653,1848.2244414547642,0.5933609958506224,732.9988734493238,1.0,1462,366,366,3.9945355191256833,5716.824553067119,0.5465116279069767,980.4592083598991,0.8461538461538461
hgb_price_context_exact_daily_top4_h30_p0.400000,False,30,4,0.4,78,458,118,121,3.7851239669421486,1800.8803633372813,0.5982532751091703,732.9988734493238,1.0,1353,352,366,3.69672131147541,6315.898724479054,0.5587583148558758,953.9901487722937,0.8461538461538461

## Passing Candidates

policy_id,passed_exact_daily_gate,horizon_minutes,daily_top_k,probability_floor,feature_count,selector_trade_count,selector_active_day_count,selector_calendar_day_count,selector_avg_trades_per_calendar_day,selector_total_net_pnl_bps,selector_win_rate,selector_max_drawdown_bps,selector_calendar_positive_month_rate,holdout_trade_count,holdout_active_day_count,holdout_calendar_day_count,holdout_avg_trades_per_calendar_day,holdout_total_net_pnl_bps,holdout_win_rate,holdout_max_drawdown_bps,holdout_calendar_positive_month_rate
hgb_price_context_exact_daily_top5_h30_p0.000000,True,30,5,0.0,78,602,121,121,4.975206611570248,2623.5797323484658,0.5863787375415282,821.5103085304067,1.0,1827,366,366,4.991803278688525,6208.386342118734,0.5500821018062397,734.4338897606749,0.7692307692307693
hgb_price_context_exact_daily_top2_h30_p0.000000,True,30,2,0.0,78,242,121,121,2.0,1064.4193121412661,0.6074380165289256,589.3653545272035,0.8,732,366,366,2.0,4097.325367542093,0.5532786885245902,629.4762493222556,0.9230769230769231
hgb_price_context_exact_daily_top1_h30_p0.000000,True,30,1,0.0,78,121,121,121,1.0,488.7429868781322,0.6363636363636364,367.80180896583494,0.6,366,366,366,1.0,3939.1315703056002,0.5846994535519126,388.08668770208806,0.9230769230769231

## Interpretation

V107 adds prior high/low, rolling range-position, realized-volatility, and prior-volume z-score features to the V106 exact-daily classifier. All new rolling features use prior bars only. This remains a research candidate, not a live trading guarantee.
