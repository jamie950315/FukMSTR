# Research V91 ETHUSDC V90 Transfer Test Results

## Decision

- Symbol: `ETHUSDC`
- Data start: `2024-06-01T00:00:00+00:00`
- Data end: `2026-06-12T23:59:00+00:00`
- Two-year start: `2024-06-12T23:59:00+00:00`
- Two-year end: `2026-06-12T23:59:00+00:00`
- Stable policies: `0` / `3`
- Best stable policy: `None`

## Policy Table

policy,stable_enough,failed_checks,trade_count,total_net_pnl_bps,mean_net_pnl_bps,win_rate,max_drawdown_bps,required_extra_cost_total_net_pnl_bps,worst_delay_total_net_pnl_bps,active_positive_month_rate,calendar_positive_month_rate,rolling_3m_positive_rate,rolling_6m_positive_rate,rolling_12m_positive_rate,rolling_3m_worst_net_pnl_bps,rolling_6m_worst_net_pnl_bps
v89_mechanical_remove_hours_0_2_3_4,False,total_net_pnl;mean_net_pnl;win_rate;active_month_positive_rate;quarter_positive_rate;rolling_3m_positive_rate;rolling_6m_positive_rate;max_drawdown;delay_totals_positive;required_extra_cost_positive,257,-2206.5050603719537,-8.58562280300371,0.49416342412451364,6947.471874638417,-6318.505060371954,-2206.5050603719537,0.5833333333333334,0.56,0.34782608695652173,0.25,0.07142857142857142,-2869.233450097788,-3048.1229921098843
v89_conservative_same_family_-550,False,total_net_pnl;mean_net_pnl;active_month_positive_rate;quarter_positive_rate;rolling_3m_positive_rate;rolling_6m_positive_rate;max_drawdown;delay_totals_positive;required_extra_cost_positive,307,-2678.6901908092686,-8.725375214362439,0.504885993485342,8584.979145006298,-7590.690190809269,-2678.6901908092686,0.5,0.48,0.391304347826087,0.4,0.14285714285714285,-3748.465934844035,-4897.5909771794995
v69_v87_oversold_short_veto_-650,False,total_net_pnl;mean_net_pnl;win_rate;active_month_positive_rate;quarter_positive_rate;rolling_3m_positive_rate;rolling_6m_positive_rate;max_drawdown;delay_totals_positive;required_extra_cost_positive,326,-2743.699641307485,-8.416256568427867,0.49693251533742333,7649.031358528746,-7959.699641307487,-3076.0914409711722,0.5,0.48,0.391304347826087,0.3,0.07142857142857142,-3244.1204124260703,-4125.673781126483

## Interpretation

This is a direct ETHUSDC transfer test of the fixed BTCUSDC V90 policy family. It does not retune thresholds or hour filters for ETHUSDC.

Passing this test would indicate transferability evidence; failing it means the BTCUSDC edge should not be assumed to work on ETHUSDC without separate design work.
