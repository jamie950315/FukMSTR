# Research V168 BTCUSDC Execution Readiness Gate

## Decision

- Status: `execution_readiness_warning`
- Promote to live: `False`
- Message: Some months require maker-only or skip-if-not-maker execution before any live use.
- Maker-only required months: `2`
- Maker-priority required months: `4`
- Mixed execution allowed months: `0`
- Taker allowed months: `18`
- Strictest month: `2024-07`
- Strictest required maker share: `0.9289774959200844`

## Gate Rules

- `required_maker_share >= 0.8`: maker-only required; taker execution should be blocked.
- `0.5 <= required_maker_share < 0.8`: maker-priority required; skip if maker or low-cost execution is unavailable.
- `0 < required_maker_share < 0.5`: mixed execution allowed, but taker share must be capped.
- `required_maker_share == 0`: normal cost monitoring.
- This gate does not add trades, change sides, change strategy thresholds, or promote live trading.

## Mode Summary

execution_readiness_mode,live_gate_action,month_count,avg_required_maker_share_pct,max_required_maker_share_pct
maker_only_required,block_taker_execution,2,87.62038601738578,92.89774959200844
maker_priority_required,prefer_maker_or_skip,4,67.15575929007468,78.18105815337084
taker_allowed,normal_cost_monitoring,18,0.0,0.0

## Monthly Readiness Gate

month,execution_readiness_mode,live_gate_action,max_taker_share_pct,required_maker_share_pct,breakeven_extra_cost_bps,base_return_pct,trade_count
2024-07,maker_only_required,block_taker_execution,7.10225040799157,92.89774959200844,0.2840900163196631,0.1971518110092143,16
2026-01,maker_only_required,block_taker_execution,17.656977557236868,82.34302244276313,0.7062791022894749,0.7397770821813129,31
2025-09,maker_priority_required,prefer_maker_or_skip,21.81894184662915,78.18105815337084,0.8727576738651663,0.2042252956844489,11
2025-05,maker_priority_required,prefer_maker_or_skip,27.3220586844874,72.6779413155126,1.0928823473794962,0.6349404227379298,29
2026-05,maker_priority_required,prefer_maker_or_skip,36.44405603372019,63.55594396627981,1.4577622413488076,0.7321121743423837,18
2025-08,maker_priority_required,prefer_maker_or_skip,45.791906274864544,54.20809372513546,1.8316762509945816,0.7933855825033861,19
2025-03,taker_allowed,normal_cost_monitoring,100.0,0.0,26.32140289279097,46.9984540896351,55
2024-08,taker_allowed,normal_cost_monitoring,100.0,0.0,28.417419650340264,25.42538104276911,28
2025-06,taker_allowed,normal_cost_monitoring,100.0,0.0,4.703845921709186,0.9954109215290434,14
2024-10,taker_allowed,normal_cost_monitoring,100.0,0.0,4.875089359788385,1.4988065081276394,17
2024-09,taker_allowed,normal_cost_monitoring,100.0,0.0,9.89976991510333,1.9000216866898656,11
2025-04,taker_allowed,normal_cost_monitoring,100.0,0.0,10.363885578171034,5.13561580615835,25
2025-07,taker_allowed,normal_cost_monitoring,100.0,0.0,10.91728884647687,3.0909574046587633,23
2026-06,taker_allowed,normal_cost_monitoring,100.0,0.0,225.0562780978925,322.9967569575514,32
2025-01,taker_allowed,normal_cost_monitoring,100.0,0.0,60.35911688616047,72.29325767511403,21
2026-04,taker_allowed,normal_cost_monitoring,100.0,0.0,20.16398633863844,13.723884638013793,12
2025-12,taker_allowed,normal_cost_monitoring,100.0,0.0,31.65640662450028,32.31747951412736,21
2025-02,taker_allowed,normal_cost_monitoring,100.0,0.0,62.73996582883487,122.05670474868052,31
2026-03,taker_allowed,normal_cost_monitoring,100.0,0.0,64.65309274598714,65.63438136096796,28
2025-11,taker_allowed,normal_cost_monitoring,100.0,0.0,73.92068046444795,122.00332461060664,46
2024-11,taker_allowed,normal_cost_monitoring,100.0,0.0,90.4802311356451,146.69262429672185,37
2026-02,taker_allowed,normal_cost_monitoring,100.0,0.0,132.23777041002413,376.70615350176143,54
2024-12,taker_allowed,normal_cost_monitoring,100.0,0.0,205.68033932483544,435.21199347865945,29
2025-10,taker_allowed,normal_cost_monitoring,100.0,0.0,403.42780511357705,617.4045998990301,37

## Interpretation

V168 turns V166 cost budgets into execution actions. The most fragile months should not be traded with mostly-taker fills. If maker or otherwise low-cost execution cannot be verified, those months should be treated as not ready for live use.

This is a research execution gate, not a live trading guarantee.
