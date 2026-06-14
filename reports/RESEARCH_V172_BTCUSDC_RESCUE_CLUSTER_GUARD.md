# Research V172 BTCUSDC Rescue Cluster Guard

## Decision

- Status: `rescue_cluster_guard_no_candidate`
- Promote to live: `False`
- Selected policy: `v162_baseline_no_cluster_guard`
- Return delta: `0.0` pct
- Drawdown improvement: `0.0` pct
- Worst-month improvement: `0.0` pct
- Guarded trades: `0`
- Message: Rescue cluster controls are evaluated as causal risk guards only, not as new entry signals.

## Guard Rules

- Base path: V162 selected account path.
- Guarded trades: rescue trades only.
- Cluster context is causal: only same-side rescue trades before the current trade are counted.
- This audit does not add trades, change side, change thresholds, or promote live trading.

## Baseline Max Drawdown

max_drawdown_pct,peak_timestamp,trough_timestamp
-32.48404826334854,2026-02-02 03:40:00+00:00,2026-02-03 18:30:00+00:00

## Selected Max Drawdown

max_drawdown_pct,peak_timestamp,trough_timestamp
-32.48404826334854,2026-02-02 03:40:00+00:00,2026-02-03 18:30:00+00:00

## Policy Comparison

policy,trade_count,guarded_trade_count,total_account_return_pct,max_drawdown_pct,positive_months,month_count,worst_month_pct,win_rate_pct,return_delta_pct,return_retention_rate,drawdown_improvement_pct,worst_month_improvement_pct,positive_month_delta,guard_passed,guard_score
v162_baseline_no_cluster_guard,645,0,2415.387400509261,-32.48404826334854,24,24,0.19715181100921397,60.62015503875969,0.0,1.0,0.0,0.0,0,False,0.0
v172_120m_half_after_2,645,20,2309.3804502491416,-32.360803047848094,23,24,-0.7826530723227696,60.62015503875969,-106.00695026011954,0.9561118227917522,0.12324521550044665,-0.9798048833319836,-1,False,-6.786711266857843
v172_120m_skip_after_2,645,20,2203.373499989021,-34.127803132032,23,24,-2.20024656738347,58.29457364341085,-212.01390052023999,0.912223645583504,-1.6437548686834589,-2.3973983783926838,-1,False,-33.66481858920281
v172_240m_half_after_2,645,27,2291.4570675143846,-36.03591302484108,23,24,-1.3738255257323624,60.62015503875969,-123.93033299487661,0.9486913225726246,-3.5518647614925385,-1.5709773367415765,-1,False,-47.2021409585308
v172_240m_half_after_1,645,46,2058.434029276622,-37.380134489930924,22,24,-2.5842325572537104,60.62015503875969,-356.95337123263926,0.8522169275382578,-4.8960862265823835,-2.7813843682629242,-2,False,-72.30685153179124
v172_120m_half_after_1,645,40,2068.176720753192,-38.36892295966584,22,24,-1.9379414026685795,60.62015503875969,-347.2106797560691,0.8562505212692328,-5.884874696317297,-2.1350932136777936,-2,False,-78.46842662668332
v172_240m_skip_after_2,645,27,2167.526734519508,-49.209860763269944,23,24,-3.3825914742026555,57.519379844961236,-247.86066598975322,0.8973826451452491,-16.725812499921403,-3.5797432852118694,-1,False,-191.46405474506844
v172_240m_skip_after_1,645,46,1701.4806580439827,-51.898303693449634,21,24,-11.109305484857414,55.348837209302324,-713.9067424652785,0.7044338550765156,-19.414255430101093,-11.306457295866627,-3,False,-267.25297562964965
v172_120m_skip_after_1,645,40,1720.9660409971223,-53.87588063291935,21,24,-11.109305484857414,55.81395348837209,-694.4213595121389,0.7125010425384654,-21.391832369570807,-11.306457295866627,-3,False,-286.339037365284

## Selected Guarded Profile

v172_policy,v172_guard_applied,side,leg,trade_count,account_return_pct,original_account_return_pct,win_rate_pct,avg_prior_same_side_rescue_count,avg_multiplier
v162_baseline_no_cluster_guard,False,long,base,437,1400.1828534040203,1400.1828534040203,58.58123569794051,0.0,1.0
v162_baseline_no_cluster_guard,False,long,rescue,76,894.2403559275327,894.2403559275327,69.73684210526315,0.0,1.0
v162_baseline_no_cluster_guard,False,short,base,113,78.56052732490768,78.56052732490768,61.06194690265486,0.0,1.0
v162_baseline_no_cluster_guard,False,short,rescue,19,42.40366385280068,42.40366385280068,68.42105263157895,0.0,1.0

## Interpretation

V172 tests whether short-horizon same-side rescue clustering explains the V171 max-drawdown cluster. Use the result as risk-research evidence only. It does not prove future live performance.

This is a research audit, not a live trading guarantee.
