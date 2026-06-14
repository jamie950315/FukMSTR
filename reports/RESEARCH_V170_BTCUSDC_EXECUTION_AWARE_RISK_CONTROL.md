# Research V170 BTCUSDC Execution-Aware Risk Control

## Decision

- Status: `execution_aware_risk_control_no_candidate`
- Promote to live: `False`
- Selected policy: `v162_baseline_no_execution_filter`
- Return delta: `0.0` pct
- Drawdown improvement: `0.0` pct
- Worst-month improvement: `0.0` pct
- Executed trades: `645` / `645` baseline
- Message: Execution-aware controls are evaluated as risk controls only, not as new entry signals.

## Policy Rules

- Base trades: V162 selected account path.
- Execution mode: V168 monthly execution readiness gate.
- V170 does not add trades, change side, change threshold, or promote live trading.
- Policies only scale or skip existing trades in maker-only, maker-priority, or no-trade-unless-cost-improves months.

## Policy Comparison

policy,trade_count,executed_trade_count,skipped_trade_count,total_account_return_pct,max_drawdown_pct,positive_months,month_count,worst_month_pct,win_rate_pct,return_delta_pct,return_retention_rate,drawdown_improvement_pct,worst_month_improvement_pct,positive_month_delta,executed_trade_delta,risk_control_passed,risk_control_score
v162_baseline_no_execution_filter,645,645,0,2415.387400509261,-32.48404826334854,24,24,0.19715181100921397,60.62015503875969,0.0,1.0,0.0,0.0,0,0,True,0.0
v170_fragile_half,645,645,0,2413.7366043250317,-32.48404826334854,24,24,0.09857590550460699,60.62015503875969,-1.6507961842294208,0.9993165501385486,0.0,-0.09857590550460699,0,0,False,-0.5093874893653292
v170_maker_only_skip,645,598,47,2414.450471616071,-32.48404826334854,22,24,0.0,61.03678929765886,-0.9369288931902702,0.9996120999500979,0.0,-0.19715181100921397,-2,-47,False,-4.995128343977973
v170_maker_only_skip_priority_half,645,598,47,2413.2681398784366,-32.48404826334854,22,24,0.0,61.03678929765886,-2.119260630824556,0.9991226001135977,0.0,-0.19715181100921397,-2,-47,False,-5.006951661354315
v170_fragile_skip,645,521,124,2412.0858081408023,-32.48404826334854,18,24,0.0,61.228406909788866,-3.3015923684588415,0.9986331002770973,0.0,-0.19715181100921397,-6,-124,False,-13.01877497873066

## Selected Monthly Path

month,execution_readiness_mode,live_gate_action,trade_count,executed_trade_count,account_return_pct,account_pnl_bps,avg_execution_multiplier
2024-07,maker_only_required,block_taker_execution,16,16,0.19715181100921397,19.71518110092184,1.0
2024-08,taker_allowed,normal_cost_monitoring,28,28,25.425381042769118,2542.538104276912,1.0
2024-09,taker_allowed,normal_cost_monitoring,11,11,1.9000216866898654,190.00216866898649,1.0
2024-10,taker_allowed,normal_cost_monitoring,17,17,1.4988065081276385,149.88065081276375,1.0
2024-11,taker_allowed,normal_cost_monitoring,37,37,146.69262429672187,14669.262429672188,1.0
2024-12,taker_allowed,normal_cost_monitoring,29,29,435.2119934786595,43521.19934786594,1.0
2025-01,taker_allowed,normal_cost_monitoring,21,21,72.29325767511403,7229.325767511403,1.0
2025-02,taker_allowed,normal_cost_monitoring,31,31,122.05670474868053,12205.670474868053,1.0
2025-03,taker_allowed,normal_cost_monitoring,55,55,46.99845408963509,4699.845408963509,1.0
2025-04,taker_allowed,normal_cost_monitoring,25,25,5.135615806158352,513.5615806158347,1.0
2025-05,maker_priority_required,prefer_maker_or_skip,29,29,0.6349404227379305,63.494042273792914,1.0
2025-06,taker_allowed,normal_cost_monitoring,14,14,0.995410921529043,99.5410921529044,1.0
2025-07,taker_allowed,normal_cost_monitoring,23,23,3.090957404658764,309.09574046587636,1.0
2025-08,maker_priority_required,prefer_maker_or_skip,19,19,0.7933855825033861,79.33855825033865,1.0
2025-09,maker_priority_required,prefer_maker_or_skip,11,11,0.20422529568444892,20.42252956844485,1.0
2025-10,taker_allowed,normal_cost_monitoring,37,37,617.4045998990302,61740.45998990302,1.0
2025-11,taker_allowed,normal_cost_monitoring,46,46,122.00332461060664,12200.332461060669,1.0
2025-12,taker_allowed,normal_cost_monitoring,21,21,32.31747951412736,3231.747951412736,1.0
2026-01,maker_only_required,block_taker_execution,31,31,0.7397770821813164,73.97770821813147,1.0
2026-02,taker_allowed,normal_cost_monitoring,54,54,376.7061535017615,37670.61535017615,1.0
2026-03,taker_allowed,normal_cost_monitoring,28,28,65.63438136096796,6563.438136096796,1.0
2026-04,taker_allowed,normal_cost_monitoring,12,12,13.723884638013788,1372.3884638013792,1.0
2026-05,maker_priority_required,prefer_maker_or_skip,18,18,0.7321121743423837,73.21121743423839,1.0
2026-06,taker_allowed,normal_cost_monitoring,32,32,322.9967569575514,32299.675695755144,1.0

## Selected Mode Profile

v170_policy,execution_readiness_mode,live_gate_action,trade_count,executed_trade_count,account_return_pct,account_pnl_bps,win_rate_pct,avg_execution_multiplier
v162_baseline_no_execution_filter,maker_only_required,block_taker_execution,47,47,0.9369288931905299,93.69288931905312,55.319148936170215,1.0
v162_baseline_no_execution_filter,maker_priority_required,prefer_maker_or_skip,77,77,2.364663475268149,236.46634752681484,59.74025974025974,1.0
v162_baseline_no_execution_filter,taker_allowed,normal_cost_monitoring,521,521,2412.085808140803,241208.58081408025,61.228406909788866,1.0

## Interpretation

V170 checks whether V169 fragile execution months should be treated as a risk-control layer. The result should be used as execution context only. It is not evidence that market emotion or trend should become a standalone entry signal.

This is a research audit, not a live trading guarantee.
