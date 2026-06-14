# Research V51/V52 Results: BTCUSDC Holdout and Formal Family Probe

V51/V52 continues from V50. V50 found a large hindsight oracle gap in full BTCUSDC aggTrade flow, but non-oracle selectors failed. This run checks whether the positive V50 family-level clue can survive a cleaner design-period / holdout-period split and a formal ledger reconstruction.

## Inputs

```text
runs/research_v50_btcusdc_full_aggtrade_flow_input/btcusdc_full_aggtrade_1m_flow_bars.csv
runs/research_v50_btcusdc_full_aggtrade_flow_quick_probe/flow_rule_candidate_folds.csv
```

The full aggTrade flow bars remain unchanged:

| Item | Value |
|---|---:|
| aggTrade rows | 259,997,196 |
| 1m flow bars | 1,278,095 |
| Date range | 2024-01-04 12:31 UTC through 2026-06-10 23:59 UTC |

## V51 Holdout Selector Diagnostic

V51 uses folds 1-4 as the design period and folds 5-7 as the holdout period. The goal is to avoid selecting a rule with knowledge of 2026 validation results.

Output:

```text
runs/research_v51_btcusdc_holdout_selector_diagnostics
```

Strict single-policy design selectors failed:

| Selector | Design result | Holdout result |
|---|---:|---:|
| active4/pass3 by design total | +3415.8688 bps | -2021.7586 bps |
| active3/pass3 by design total | +3794.0248 bps | -347.0821 bps |
| active4 by design min | +622.4568 bps | -587.3112 bps |

There were no policies that were active and profitable in all four design folds.

The best holdout policies were not identifiable from the design period. The top holdout rule, `1440|720|flow_momentum|range_bps|0.9`, had zero design-period activity and +5592.4117 bps in holdout. Across all 542 policies, design-period total and holdout total had essentially no rank correlation:

```text
Spearman correlation: -0.0260
Pearson correlation:   0.0036
```

This supports the root-cause diagnosis from V50: the blocker is selection stability.

## V51 Family-Level Diagnostic

A coarser family selector found a tempting clue:

```text
horizon=1440
direction=flow_momentum
filter=range_bps
quantile=0.85
```

At the family-summary level this looked positive:

| Metric | Value |
|---|---:|
| Design active folds | 4 |
| Design passed folds | 3 |
| Design total | +2942.7940 bps |
| Holdout active folds | 3 |
| Holdout passed folds | 2 |
| Holdout total | +2397.7795 bps |
| Full total | +5340.5736 bps |

However, this was only a quick-probe aggregate and not a formal trade ledger.

## Ledger Rebuild Check

Attempting to rebuild the V51 family ledger from the V50 quick-probe candidate rows exposed a mismatch. The quick-probe candidate totals could not be reproduced with the project ledger logic. Example:

| Fold | Lookback | V50 trades | Rebuilt trades | V50 total | Rebuilt total |
|---:|---:|---:|---:|---:|---:|
| 1 | 30 | 69 | 60 | +506.0846 | +2366.8104 |
| 5 | 240 | 36 | 60 | +1545.0225 | -3171.3863 |
| 6 | 1440 | 19 | 60 | +1305.8686 | -3004.3165 |
| 7 | 60 | 74 | 60 | -380.7379 | -2132.7099 |

The V50 quick probe remains useful as an exploration tool, but it is not strong enough as final evidence. V52 therefore reruns a narrowed version through the formal candidate and ledger functions.

## V52 Formal Family Probe

Output:

```text
runs/research_v52_btcusdc_formal_family_probe
```

Formal candidate scope:

```text
horizon: 1440 minutes
direction: flow_momentum
filter: range_bps
lookbacks: 15, 30, 60, 120, 240, 480, 720, 1440 minutes
quantiles: 0.80, 0.85, 0.90
cost: 8.5 bps
folds: same 7 chronological folds as V50
```

The best full-period formal single policy was positive but not selectable cleanly from the design period:

| Policy | Full total | Design total | Design passed | Holdout total | Holdout passed | Worst active fold |
|---|---:|---:|---:|---:|---:|---:|
| `1440|30|flow_momentum|range_bps|0.8` | +3082.5335 | +186.0017 | 2/4 | +2896.5319 | 2/3 | -927.8707 |

The design-only selectors failed:

| Selector | Selected policy | Design total | Holdout total | Holdout passed |
|---|---|---:|---:|---:|
| strict active4/pass4 | none | n/a | n/a | n/a |
| active4/pass3 by design total | `1440|1440|flow_momentum|range_bps|0.85` | +3028.2071 | -3009.0988 | 0/3 |
| active3/pass3 by design total | `1440|1440|flow_momentum|range_bps|0.85` | +3028.2071 | -3009.0988 | 0/3 |
| active4 by design min | `1440|1440|flow_momentum|range_bps|0.85` | +3028.2071 | -3009.0988 | 0/3 |

The formal equal-weight family checks were also negative:

| Quantile | Design total | Holdout total | Full total |
|---:|---:|---:|---:|
| 0.90 | +354.0055 | -1395.7263 | -1041.7208 |
| 0.80 | -610.0300 | -590.6319 | -1200.6619 |
| 0.85 | -298.1101 | -1188.0299 | -1486.1400 |

## Formal Prequential Check

The best narrowed-family prequential selector was still too weak:

| Warmup | Rule | Active folds | Passed folds | Total | Worst active fold |
|---:|---|---:|---:|---:|---:|
| 3 | prior_pass_total | 2 | 1 | +468.6743 bps | -873.6133 bps |

This does not meet the target because it is sparse and still has a materially negative active fold.

## Conclusion

V51/V52 does not achieve the target. The positive family clue from V50 does not survive formal ledger verification. The current root cause remains selection instability: hindsight-profitable BTCUSDC aggTrade flow candidates exist, but design-period evidence still fails to select a stable future winner without using holdout information.

