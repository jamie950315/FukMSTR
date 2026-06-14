# BTCUSDC Fixed Flow V68 Design

## Goal

Find a new BTCUSDC method that can produce positive income on true BTCUSDC public data without reusing the failed BTC-to-BTCUSDC proxy or relying on validation-oracle selection.

## Current Evidence

The V26 true BTCUSDC replay failed badly on the full available public replay. The V54-V67 sparse take-profit route also closed as not promotable because it failed true replay and dense delay robustness.

V50 showed that full available BTCUSDC aggTrade flow contains hindsight-profitable fixed policies, but non-oracle selectors failed. The most promising next step is therefore a fixed-policy stability audit, not another selector.

## Candidate

V68 starts with the strongest V50 fixed policy:

- Lookback: 1440 minutes
- Horizon: 720 minutes
- Direction: `flow_momentum`
- Filter feature: `range_bps`
- Threshold source: quantile `0.9`
- Fee: 8.5 bps round trip
- Leverage for account-return reporting: 8x

The threshold is computed once from the full input bars only to reproduce the fixed policy family. The audit does not choose a new policy from validation results.

## Stability Checks

The method is considered a research candidate only if all checks pass:

- Full fixed-policy net PnL is positive.
- Trade count is at least 50.
- At least 5 chronological folds are active.
- At least 70% of active folds have positive net PnL.
- Worst active fold net PnL is no worse than -500 bps.
- Delay stress over 0, 1, 2, 5, and 10 minutes remains positive in total.
- Worst delay total net PnL is positive.
- Extra-cost stress of 0, 4, 8, and 16 bps per trade keeps the 0 bps and 4 bps cases positive.

## Outputs

V68 writes:

- `runs/research_v68_btcusdc_fixed_flow_stability/v68_summary.json`
- `runs/research_v68_btcusdc_fixed_flow_stability/v68_base_trade_ledger.csv`
- `runs/research_v68_btcusdc_fixed_flow_stability/v68_fold_summary.csv`
- `runs/research_v68_btcusdc_fixed_flow_stability/v68_delay_summary.csv`
- `runs/research_v68_btcusdc_fixed_flow_stability/v68_extra_cost_summary.csv`
- `reports/RESEARCH_V68_FIXED_FLOW_STABILITY_RESULTS.md`

## Decision Rule

If V68 passes, it is a new positive-income research candidate. If it fails, the report must say which requirement failed and the investigation should move to a stricter regime-gated fixed policy rather than changing thresholds to force a pass.
