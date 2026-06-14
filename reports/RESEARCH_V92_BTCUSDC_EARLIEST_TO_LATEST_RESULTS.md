# Research V92 BTCUSDC Earliest-to-Latest Results

## Decision

- Requested through date: `2026-06-13`
- Latest available data end: `2026-06-12T23:59:00+00:00`
- Full-window start: `2024-01-04T12:31:00+00:00`
- Full-window end: `2026-06-12T23:59:00+00:00`
- Stable policies: `2` / `3`
- Best stable policy: `v89_conservative_same_family_-550`

## Policy Table

policy,stable_enough,failed_checks,trade_count,total_net_pnl_bps,mean_net_pnl_bps,win_rate,max_drawdown_bps,required_extra_cost_total_net_pnl_bps,worst_delay_total_net_pnl_bps,active_positive_month_rate,calendar_positive_month_rate,quarter_positive_rate,rolling_3m_positive_rate,rolling_6m_positive_rate,rolling_12m_positive_rate,rolling_3m_worst_net_pnl_bps,rolling_6m_worst_net_pnl_bps,rolling_12m_worst_net_pnl_bps
v89_conservative_same_family_-550,True,,159,6302.162485573197,39.63624204763017,0.5849056603773585,1408.2340595779938,3758.162485573198,5877.415065356098,0.6538461538461539,0.5666666666666667,0.8,0.8214285714285714,0.8,1.0,-930.8951771343568,-842.9808045544295,468.4018257639025
v89_mechanical_remove_hours_0_2_3_4,True,,140,6019.930411719794,42.99950294085568,0.5785714285714286,1541.7677989584176,3779.9304117197935,5541.884484410617,0.64,0.5333333333333333,0.9,0.7857142857142857,0.8,1.0,-729.714875137055,-641.8005025571276,154.7152768230219
v69_v87_oversold_short_veto_-650,False,active_month_positive_rate;rolling_6m_positive_rate,175,5316.35343838643,30.379162505065313,0.5542857142857143,1581.729863502358,2516.353438386429,5032.294577459663,0.5384615384615384,0.4666666666666667,0.8,0.75,0.72,0.8421052631578947,-1278.0427280814833,-1223.385663638611,-589.4556695585685

## Interpretation

This run applies the fixed V90 BTCUSDC policy family to the full available BTCUSDC aggTrade flow bar window. It does not retune thresholds.

The requested current date is included only if Binance has already published a complete daily file for that date. At this run time, the available data ends at the latest complete public file present in the local data set.
