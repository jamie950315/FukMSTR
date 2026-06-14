# Research V163 BTCUSDC Post V162 Candidate Audit

## Decision

- Status: `post_v162_no_clean_candidate`
- Promote to next model: `False`
- Message: No clean independent post-V162 candidate cleared the promotion gate.
- Selector period: `< 2026-01-01T00:00:00+00:00`
- Holdout period: `>= 2026-01-01T00:00:00+00:00`

## Audit Rules

- Base: V162 selected account path.
- Excluded post-trade or account-path result fields, including `drawdown_pct`, returns, pnl, equity, flags, and modifiers.
- Excluded already-promoted same-family fields: `day_sofar_count`, `trend_follow_1440_bps`, and duplicate `prior_ret_1440_bps`.
- Minimum changed trades: selector `60`, holdout `20`.
- Minimum full-period improvement before promotion: `1.005`.
- Holdout is used only for validation.

## Baseline

policy,trade_count,total_account_return_pct,max_drawdown_pct,positive_months,month_count,worst_month_pct,win_rate
v162_full,645,2415.387400509261,-32.48404826334854,24,24,0.19715181100921397,0.6062015503875969
v162_selector,470,1634.8543347944433,-28.69875051863687,18,18,0.19715181100921397,0.6
v162_holdout,175,780.5330657148182,-32.48404826334856,6,6,0.7321121743423837,0.6228571428571429

## Scan Summary

{
  "eligible_conditions": 3392,
  "evaluated_candidates": 13568,
  "feature_count": 72,
  "risk_checked_candidates": 5339
}

## Rejection Summary

reason,count
full_return_lt_minimum,8210
full_drawdown_worse,4537
too_few_changed_trades,4024
selector_drawdown_worse,758
holdout_drawdown_worse,21
full_worst_month_worse,19
holdout_not_better,17
holdout_worst_month_worse,4
selector_not_better,2

## Interpretation

No clean, independent post-V162 candidate cleared the promotion gate. The large candidates found before this audit depended on `drawdown_pct`, which is treated as unsuitable for entry-time promotion. The correct action is to keep V162 fixed and avoid adding another weak historical overlay.

This is a research audit, not a live trading guarantee.
