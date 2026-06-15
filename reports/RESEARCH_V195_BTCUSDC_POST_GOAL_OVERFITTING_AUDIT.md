# Research V195 BTCUSDC Post-Goal Overfitting Audit

## Decision

- Status: `post_goal_overfitting_warning`
- Promote to live: `False`
- Highest risk version: `V194`
- Stop historical optimization: `True`
- Recommendation: `freeze_historical_optimization_and_forward_monitor`
- V194 high concentration risk: `True`
- Holdout reuse risk: `True`
- Message: V194 shows high concentration risk; freeze historical optimization and validate on new forward data.

## Required Iteration Metrics

| Metric | V193 | V194 |
|---|---:|---:|
| Account return estimate | +3950.66% | +4044.70% |
| Improvement | - | +94.04 percentage points |
| Max drawdown | -30.20% | -30.20% |
| Positive months | 24/24 | 24/24 |
| Holdout return | +1386.21% | +1452.80% |
| Holdout months | 6/6 | 6/6 |

## Audit Rules

- V195 is an audit, not a new strategy overlay.
- It checks the improvement added during V192, V193, and V194.
- Month concentration warning threshold: `50.0` pct of total improvement.
- Single-trade concentration warning threshold: `30.0` pct of affected absolute delta.
- Minimum active months: `8`.
- The V192-V194 holdout has been reused for selection and should no longer be treated as clean validation.

## Version Metrics

version,account_return_pct,improvement_pct,max_drawdown_pct,positive_months,holdout_return_pct,holdout_months
V191,3917.6020112932893,-,-30.199288542202567,24/24,1370.2428788017883,6/6
V192,3930.9840274639096,13.382016170620318,-30.199288542202567,24/24,1377.770488779958,6/6
V193,3950.655016371391,19.670988907481387,-30.199288542202567,24/24,1386.2068824078733,6/6
V194,4044.6984352611944,94.04341888980343,-30.199288542202567,24/24,1452.8046591294067,6/6

## Overfitting Concentration Table

version,previous_version,return_delta_pct,holdout_return_delta_pct,holdout_delta_share_pct,affected_trade_count,affected_active_month_count,top_delta_month,top_month_delta_pct,top_month_delta_share_pct,top_single_delta_share_pct,affected_win_rate_pct
V192,V191,13.382016170620933,7.527609978169663,56.2516879533884,37,13,2024-07,4.738078058978348,35.40630947211371,18.211971526969485,48.64864864864865
V193,V192,19.67098890748124,8.43639362791544,42.88749115560185,18,10,2026-01,4.72834809511429,24.037165174324365,15.8310515423418,0.0
V194,V193,94.04341888980343,66.59777672153339,70.8159885165066,37,9,2026-02,58.71270405557677,62.43148616744158,33.6977118349542,75.67567567567568

## Interpretation

V192 and V193 are lower-risk risk-reduction changes. V194 adds a large improvement, but the gain is concentrated in one holdout month and one large affected trade. That concentration is a practical overfitting warning.

Recommended next step: freeze historical optimization, keep V194 as an aggressive research candidate, keep V193 as the more conservative comparison, and validate both through forward monitoring on new data.

This is a research audit, not a live trading guarantee.
