# Research V90 BTCUSDC Two-Year Window Results

## Decision

- Data end: `2026-06-12T23:59:00+00:00`
- Two-year start: `2024-06-12T23:59:00+00:00`
- Two-year end: `2026-06-12T23:59:00+00:00`
- Stable policies: `2` / `3`
- Best stable policy: `v89_mechanical_remove_hours_0_2_3_4`

## Policy Table

policy,stable_enough,failed_checks,trade_count,total_net_pnl_bps,mean_net_pnl_bps,win_rate,max_drawdown_bps,required_extra_cost_total_net_pnl_bps,worst_delay_total_net_pnl_bps,active_positive_month_rate,calendar_positive_month_rate,rolling_3m_positive_rate,rolling_6m_positive_rate,rolling_12m_positive_rate,rolling_3m_worst_net_pnl_bps,rolling_6m_worst_net_pnl_bps
v89_mechanical_remove_hours_0_2_3_4,True,,102,5125.906256516064,50.25398290702024,0.6078431372549019,1541.767798958419,3493.906256516065,4616.9141625548045,0.65,0.52,0.782608695652174,0.75,1.0,-729.714875137055,-641.8005025571276
v89_conservative_same_family_-550,True,,112,4534.913159647622,40.49029606828234,0.6071428571428571,1408.2340595779942,2742.913159647622,3990.100987733619,0.6666666666666666,0.56,0.782608695652174,0.75,1.0,-930.8951771343568,-842.9808045544295
v69_v87_oversold_short_veto_-650,False,active_month_positive_rate;rolling_3m_positive_rate;rolling_6m_positive_rate,127,3660.8798382211535,28.82582549780436,0.5669291338582677,1581.7298635023571,1628.879838221153,3244.2499391701713,0.5238095238095238,0.44,0.6956521739130435,0.65,0.7857142857142857,-1278.0427280814833,-1223.385663638611

## Interpretation

This run applies the V90 data-refresh and fixed-policy reconstruction path to the most recent two years ending at the extended data end. It does not retune thresholds.

The result should be read as an updated two-year replay of the V69/V87/V89 policy variants, not as a new forward-trade proof.
