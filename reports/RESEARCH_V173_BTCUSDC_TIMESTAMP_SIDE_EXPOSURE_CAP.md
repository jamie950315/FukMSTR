# Research V173 BTCUSDC Timestamp Side Exposure Cap

## Decision

- Status: `timestamp_side_exposure_cap_no_candidate`
- Promote to live: `False`
- Selected policy: `v162_baseline_no_timestamp_side_cap`
- Return delta: `0.0` pct
- Drawdown improvement: `0.0` pct
- Worst-month improvement: `0.0` pct
- Capped trades: `0`
- Capped timestamp-side groups: `0`
- Message: Timestamp-side exposure caps are evaluated as causal sizing guards only, not as new entry signals.

## Cap Rules

- Base path: V162 selected account path.
- Cap unit: same timestamp and same side.
- Cap action: scale all trades in the timestamp-side group by `cap / group_position_weight` when the group exceeds the cap.
- This audit does not add trades, change side, change thresholds, or promote live trading.

## Baseline Max Drawdown

max_drawdown_pct,peak_timestamp,trough_timestamp
-32.48404826334854,2026-02-02 03:40:00+00:00,2026-02-03 18:30:00+00:00

## Selected Max Drawdown

max_drawdown_pct,peak_timestamp,trough_timestamp
-32.48404826334854,2026-02-02 03:40:00+00:00,2026-02-03 18:30:00+00:00

## Policy Comparison

policy,trade_count,capped_trade_count,capped_group_count,total_account_return_pct,max_drawdown_pct,positive_months,month_count,worst_month_pct,win_rate_pct,return_delta_pct,return_retention_rate,drawdown_improvement_pct,worst_month_improvement_pct,positive_month_delta,cap_passed,cap_score
v162_baseline_no_timestamp_side_cap,645,0,0,2415.387400509261,-32.48404826334854,24,24,0.19715181100921397,60.62015503875969,0.0,1.0,0.0,0.0,0,False,0.0
v173_cap_weight_8p0,645,10,5,2344.7229002676795,-32.48404826334854,24,24,0.19715181100921397,60.62015503875969,-70.66450024158166,0.9707440304496567,0.0,0.0,0,False,-1.9132900048316333
v173_cap_weight_3p5,645,92,56,1407.7796537548406,-30.29282496495489,22,24,-0.4477620750472703,60.62015503875969,-1007.6077467544205,0.5828380380960934,2.191223298393652,-0.6449138860564843,-2,False,-7.064491381434315
v173_cap_weight_2p5,645,168,132,1103.8814406414153,-27.797371405178637,21,24,-2.7191063785858933,60.62015503875969,-1311.5059598678458,0.45702045162969407,4.686676858169903,-2.916258189595107,-3,False,-7.1446415636334155
v173_cap_weight_3p0,645,95,59,1268.2139721466513,-29.490921281708665,21,24,-1.544591526701781,60.62015503875969,-1147.17342836261,0.5250561346305196,2.9931269816398753,-1.7417433377109948,-3,False,-7.6209154394084155
v173_cap_weight_6p0,645,19,13,1956.590905642439,-32.48404826334854,23,24,-0.08947658279366799,60.62015503875969,-458.79649486682206,0.8100526256077641,0.0,-0.28662839380288196,-1,False,-11.909071866350851
v173_cap_weight_5p0,645,26,17,1755.230117478176,-32.48404826334854,23,24,-0.23279077969510886,60.62015503875969,-660.1572830310852,0.7266867903294116,0.0,-0.42994259070432284,-1,False,-17.052858614143318
v173_cap_weight_4p0,645,49,32,1530.7026812988793,-32.360803047848094,23,24,-0.37610497659654984,60.62015503875969,-884.6847192103819,0.6337296787157809,0.12324521550044665,-0.5732567876057638,-1,False,-22.52752616723199

## Selected Capped Profile

v173_policy,v173_cap_applied,side,leg,trade_count,account_return_pct,original_account_return_pct,win_rate_pct,avg_timestamp_side_weight,avg_multiplier
v162_baseline_no_timestamp_side_cap,False,long,base,437,1400.1828534040203,1400.1828534040203,58.58123569794051,1.451599268710224,1.0
v162_baseline_no_timestamp_side_cap,False,long,rescue,76,894.2403559275327,894.2403559275327,69.73684210526315,3.757106808275322,1.0
v162_baseline_no_timestamp_side_cap,False,short,base,113,78.56052732490768,78.56052732490768,61.06194690265486,1.086841861023402,1.0
v162_baseline_no_timestamp_side_cap,False,short,rescue,19,42.40366385280068,42.40366385280068,68.42105263157895,3.2547070412508687,1.0

## Interpretation

V173 tests whether simultaneous same-side source stacking explains the V171 max-drawdown cluster better than prior rescue-count guards. Use the result as risk-research evidence only. It does not prove future live performance.

This is a research audit, not a live trading guarantee.
