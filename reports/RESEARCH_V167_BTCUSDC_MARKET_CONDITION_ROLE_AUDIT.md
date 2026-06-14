# Research V167 BTCUSDC Market Condition Role Audit

## Decision

- Status: `market_condition_role_audit_passed`
- Promote to live: `False`
- Message: Market condition data is useful mainly as sizing, risk, monitoring, or execution context; no direct-entry use is approved.
- Cataloged research reports: `24`
- Direct-entry allowed count: `0`
- Sizing / risk governor count: `15`
- Monitor-only count: `1`
- Macro-context-only count: `2`
- Execution-risk-control count: `2`

## Role Summary

recommended_role,research_count,promoted_count,direct_entry_allowed_count
sizing_or_risk_governor,15,15,0
candidate_scan_only,1,1,0
execution_risk_control,2,0,0
macro_context_only,2,0,0
monitor_only,1,0,0
not_promoted,1,0,0
robustness_gate,1,0,0
stop_condition,1,0,0

## Role Catalog

version,title,status,recommended_role,entry_policy,main_lesson,source_report
V143,Market emotion trend audit,selector_candidate_not_holdout_robust,not_promoted,Do not use as a standalone entry or side signal.,Raw emotion/trend boosts can raise return but did not stay robust enough for promotion.,reports/RESEARCH_V143_BTCUSDC_MARKET_EMOTION_TREND_AUDIT.md
V144,Funding sentiment governor,funding_sentiment_governor_passed,sizing_or_risk_governor,"May be used only as a small sizing, throttle, or risk governor on already-approved trades.",Funding helped as a small not-crowded contrarian sizing layer.,reports/RESEARCH_V144_BTCUSDC_FUNDING_SENTIMENT_GOVERNOR.md
V145,Derivatives sentiment monitor,derivatives_sentiment_recent_monitor_ready,monitor_only,Use only for monitoring until enough history exists for promotion testing.,Open-interest and long/short ratios were useful context but had too little history.,reports/RESEARCH_V145_BTCUSDC_DERIVATIVES_SENTIMENT_MONITOR.md
V146,Fear and Greed macro overlay,fear_greed_macro_overlay_not_promoted,macro_context_only,Use only as slow macro context; do not promote without new robust evidence.,Daily macro sentiment raised pockets of return but worsened promotion risk gates.,reports/RESEARCH_V146_BTCUSDC_FEAR_GREED_MACRO_OVERLAY.md
V147,Fear and Greed regime risk overlay,fear_greed_regime_risk_overlay_not_promoted,macro_context_only,Use only as slow macro context; do not promote without new robust evidence.,Fear and Greed risk trims did not generalize cleanly to holdout.,reports/RESEARCH_V147_BTCUSDC_FEAR_GREED_REGIME_RISK_OVERLAY.md
V148,Premium basis sentiment overlay,premium_basis_sentiment_overlay_passed,sizing_or_risk_governor,"May be used only as a small sizing, throttle, or risk governor on already-approved trades.",Premium/basis helped when used as short-term positioning context.,reports/RESEARCH_V148_BTCUSDC_PREMIUM_BASIS_SENTIMENT_OVERLAY.md
V149,Confidence persistence overlay,confidence_persistence_overlay_passed,sizing_or_risk_governor,"May be used only as a small sizing, throttle, or risk governor on already-approved trades.",Internal confidence persistence helped after external context already filtered sizing.,reports/RESEARCH_V149_BTCUSDC_CONFIDENCE_PERSISTENCE_OVERLAY.md
V150,Funding persistence overlay,funding_persistence_overlay_passed,sizing_or_risk_governor,"May be used only as a small sizing, throttle, or risk governor on already-approved trades.","Longer-horizon funding helped as sizing context, not as a new entry source.",reports/RESEARCH_V150_BTCUSDC_FUNDING_PERSISTENCE_OVERLAY.md
V151,Range alignment overlay,range_alignment_overlay_passed,sizing_or_risk_governor,"May be used only as a small sizing, throttle, or risk governor on already-approved trades.",Long-horizon range alignment helped avoid weak sizing states.,reports/RESEARCH_V151_BTCUSDC_RANGE_ALIGNMENT_OVERLAY.md
V152,Short trend activity overlay,short_trend_activity_overlay_passed,sizing_or_risk_governor,"May be used only as a small sizing, throttle, or risk governor on already-approved trades.",Short-term movement activity helped as a modest sizing layer.,reports/RESEARCH_V152_BTCUSDC_SHORT_TREND_ACTIVITY_OVERLAY.md
V153,Premium balance overlay,premium_balance_overlay_passed,sizing_or_risk_governor,"May be used only as a small sizing, throttle, or risk governor on already-approved trades.","Premium basis worked best as balance: boost calm long premium, throttle weak base-long premium.",reports/RESEARCH_V153_BTCUSDC_PREMIUM_BALANCE_OVERLAY.md
V154,Rescue funding stabilizer,rescue_funding_stabilizer_passed,sizing_or_risk_governor,"May be used only as a small sizing, throttle, or risk governor on already-approved trades.",Rescue-long was strongest when funding pressure was not extreme.,reports/RESEARCH_V154_BTCUSDC_RESCUE_FUNDING_STABILIZER.md
V155,Base long premium expansion,base_long_premium_expansion_passed,sizing_or_risk_governor,"May be used only as a small sizing, throttle, or risk governor on already-approved trades.",Calm-premium base-long states were under-sized.,reports/RESEARCH_V155_BTCUSDC_BASE_LONG_PREMIUM_EXPANSION.md
V156,Base long premium stepup,base_long_premium_stepup_passed,sizing_or_risk_governor,"May be used only as a small sizing, throttle, or risk governor on already-approved trades.",The already-promoted calm-premium base-long flag tolerated a small step-up.,reports/RESEARCH_V156_BTCUSDC_BASE_LONG_PREMIUM_STEPUP.md
V157,Market condition post-stepup audit,market_condition_overlay_passed,candidate_scan_only,Do not use as a standalone entry or side signal.,Many raw high-return candidates failed risk gates; only strict sizing overlays were safe to consider.,reports/RESEARCH_V157_BTCUSDC_MARKET_CONDITION_POST_STEPUP_AUDIT.md
V158,Base range position boost,base_range_position_boost_passed,sizing_or_risk_governor,"May be used only as a small sizing, throttle, or risk governor on already-approved trades.",Prior 1440-minute range position helped as a narrow base-trade sizing boost.,reports/RESEARCH_V158_BTCUSDC_BASE_RANGE_POSITION_BOOST.md
V159,Base trend abs boost,base_trend_abs_boost_passed,sizing_or_risk_governor,"May be used only as a small sizing, throttle, or risk governor on already-approved trades.",Large 1440-minute absolute trend move helped as base-trade sizing context.,reports/RESEARCH_V159_BTCUSDC_BASE_TREND_ABS_BOOST.md
V160,Base trend abs stepup,base_trend_abs_stepup_passed,sizing_or_risk_governor,"May be used only as a small sizing, throttle, or risk governor on already-approved trades.",The already-promoted trend-abs flag tolerated a small step-up.,reports/RESEARCH_V160_BTCUSDC_BASE_TREND_ABS_STEPUP.md
V161,Day sofar count boost,day_sofar_count_boost_passed,sizing_or_risk_governor,"May be used only as a small sizing, throttle, or risk governor on already-approved trades.",Earlier-in-day signal sequence states were under-sized.,reports/RESEARCH_V161_BTCUSDC_DAY_SOFAR_COUNT_BOOST.md
V162,Long trend follow boost,long_trend_follow_boost_passed,sizing_or_risk_governor,"May be used only as a small sizing, throttle, or risk governor on already-approved trades.",Less-adverse 1440-minute trend helped long trades as sizing context.,reports/RESEARCH_V162_BTCUSDC_LONG_TREND_FOLLOW_BOOST.md
V163,Post V162 candidate audit,post_v162_no_clean_candidate,stop_condition,Do not use as a standalone entry or side signal.,No clean independent post-V162 candidate cleared promotion gates.,reports/RESEARCH_V163_BTCUSDC_POST_V162_CANDIDATE_AUDIT.md
V164,V162 robustness audit,v162_robustness_warning,robustness_gate,Do not use as a standalone entry or side signal.,The candidate is fragile to realistic extra execution cost.,reports/RESEARCH_V164_BTCUSDC_V162_ROBUSTNESS_AUDIT.md
V165,Cost fragility audit,cost_fragility_warning,execution_risk_control,Use as execution-quality constraint before considering live use.,Some months have very small extra-cost headroom.,reports/RESEARCH_V165_BTCUSDC_COST_FRAGILITY_AUDIT.md
V166,Execution budget audit,execution_budget_warning,execution_risk_control,Use as execution-quality constraint before considering live use.,Six months require maker or otherwise low-cost execution quality under 4 bps taker extra cost.,reports/RESEARCH_V166_BTCUSDC_EXECUTION_BUDGET_AUDIT.md

## Interpretation

V167 answers the market trend/emotion question by separating data value from data use. The historical evidence does not support using market emotion or trend as a standalone entry or side selector. The evidence is stronger when these fields are used as small sizing overlays, throttles, risk governors, monitoring context, or execution constraints on trades that the base system already wants to take.

The practical rule is: market trend/emotion can help, but the wrong use is to let it become the main reason to open a trade.

This is a research audit, not a live trading guarantee.
