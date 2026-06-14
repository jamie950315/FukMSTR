# Research V09 Results

V09 continued the long-window branch after V08.  The focus remained on 45s, 60s, 90s, and 120s horizons, with most effort on the 90s diagnostic lead from V08.

## Main conclusion

Stable profit is still not established.

V09 found one meaningful improvement over V08: a **90s prequential template-transfer lead**.  It ranks fixed templates using only earlier validation folds, then tests the selected template on the next fold.  This removes the full-hindsight `validation_rank` oracle from V08.  The lead is positive after taker bid/ask execution, 0.5s latency, and 1.5 bps cost, and it passes the cost/latency stress grid, but it has only 11 trades and a negative fold bootstrap lower bound.  It is a stronger research lead, not a deployable strategy.

Two other attempts failed:

- Family-adaptive filtering: freeze the oracle-looking rule family, then allow each fold to tune numeric thresholds using calibration only.
- Calibrated-edge filtering: learn a fold-local probability-edge recalibrator from calibration rows only.

Both failed to convert the V08 oracle lead into a stable rule.

## Main code changes

- Added `src/lob_microprice_lab/family_adaptive.py`.
  - Freezes qualitative rule shape such as direction mode, signed column, and signed agreement mode.
  - Allows only numeric thresholds to adapt from each fold's calibration window.
  - CLI: `family-adaptive-audit`.
- Added `src/lob_microprice_lab/edge_calibration.py`.
  - Learns a fold-local mapping from raw model edge and stationary LOB features to calibrated up/down probability.
  - Replaces `prob_up/prob_down` before selective candidate search.
  - Supports logistic and ridge calibrators.
  - CLI: `calibrated-edge-audit`.
- Added `src/lob_microprice_lab/template_transfer.py`.
  - Builds a fixed template pool from the first calibration window.
  - Ranks templates using validation folds that have already occurred.
  - Tests the selected template on the next validation fold.
  - CLI: `template-transfer-audit`.
- Added `tests/test_v09_research_tools.py`.
- Added Makefile targets:
  - `calibrated-edge-h90-v09`
  - `family-h90-v09`
  - `template-transfer-h90-v09`

## V09 leaderboard

| Run | Type | Horizon | OOF trades | Hit rate | Mean net PnL | Total net PnL | Gate |
|---|---|---:|---:|---:|---:|---:|---|
| `research_v09_template_transfer_h90` | prequential template transfer | 90s | 11 | 81.82% | +5.4137 bps | +59.5504 bps | failed |
| `research_v09_ensemble_h90_5fold_stationary` | 5-fold ensemble diagnostic | 90s | 25 | 40.00% | +2.3576 bps | +58.9407 bps | failed |
| `research_v09_template_transfer_h45` | prequential template transfer | 45s | 3 | 66.67% | +0.8725 bps | +2.6174 bps | failed |
| `research_v09_calibrated_edge_h120_logistic` | calibrated edge | 120s | 11 | 36.36% | +0.2398 bps | +2.6378 bps | failed |
| `research_v09_calibrated_edge_h90_ridge` | calibrated edge | 90s | 15 | 46.67% | -0.1203 bps | -1.8038 bps | failed |
| `research_v09_calibrated_edge_h90_logistic` | calibrated edge | 90s | 12 | 41.67% | -0.4343 bps | -5.2121 bps | failed |
| `research_v09_calibrated_edge_h60_logistic` | calibrated edge | 60s | 14 | 64.29% | -1.2808 bps | -17.9308 bps | failed |
| `research_v09_family_h90_oracle_shape_adaptive` | family adaptive | 90s | 12 | 75.00% | -1.8433 bps | -22.1198 bps | failed |
| `research_v09_calibrated_edge_h45_logistic` | calibrated edge | 45s | 30 | 43.33% | -3.0076 bps | -90.2293 bps | failed |
| `research_v09_family_h120_oracle_shape_adaptive` | family adaptive | 120s | 7 | 57.14% | -6.1672 bps | -43.1707 bps | failed |
| `research_v09_template_transfer_h90_5fold` | 5-fold template transfer | 90s | 3 | 0.00% | -8.9121 bps | -26.7362 bps | failed |

Full table: `runs/research_v09_summary/leaderboard.csv`.

## Best V09 lead: 90s prequential template transfer

Run:

```text
runs/research_v09_template_transfer_h90
```

Settings:

```text
horizon: 90s
execution: taker bid/ask, non-overlap
cost: 1.5 bps
latency: 0.5s
template pool: first calibration window
selection rule: rank templates by past validation folds only, then test on next fold
warmup folds: 1
```

Main result:

| Metric | Value |
|---|---:|
| OOF trades | 11 |
| Hit rate | 81.82% |
| Mean net PnL | +5.4137 bps/trade |
| Total net PnL | +59.5504 bps |
| Fold min trades | 5 |
| Fold min mean net PnL | +0.7171 bps |
| Fold min bootstrap p05 | -5.4690 bps |
| Stress min mean net PnL | +1.3366 bps |
| Stress min total net PnL | +14.7031 bps |
| Shift-null p(mean >= actual) | 0.0875 |
| Shift-null p(total >= actual) | 0.0875 |

Gate result:

```text
failed checks: enough_oof_trades, positive_bootstrap_p05_min
```

Interpretation: this is a stronger lead than the V08 full-hindsight oracle because it uses past validation behavior to choose the next template.  It still has too few trades and an unstable bootstrap lower bound.

## 5-fold rerun check

V09 also retrained a 5-fold stationary H90 ensemble:

```text
runs/research_v09_ensemble_h90_5fold_stationary
```

The raw 5-fold ensemble diagnostic showed positive aggregate PnL:

| Metric | Value |
|---|---:|
| OOF trades | 25 |
| Hit rate | 40.00% |
| Mean net PnL | +2.3576 bps |
| Total net PnL | +58.9407 bps |
| Fold min mean net PnL | -5.2964 bps |
| Fold min bootstrap p05 | -16.8534 bps |

The 5-fold template-transfer audit failed badly:

| Metric | Value |
|---|---:|
| OOF trades | 3 |
| Hit rate | 0.00% |
| Mean net PnL | -8.9121 bps |
| Total net PnL | -26.7362 bps |

This weakens the 90s lead.  The positive 3-fold transfer result appears sensitive to fold construction and trade sparsity.

## Family-adaptive results

The family-adaptive idea tried to convert V08's oracle templates into reusable qualitative rule families.  It freezes only the qualitative shape and lets each fold adapt numeric thresholds from calibration.

| Run | Horizon | Family seed | OOF trades | Mean net PnL | Total net PnL | Gate |
|---|---:|---|---:|---:|---:|---|
| `research_v09_family_h90_oracle_shape_adaptive` | 90s | V08 H90 oracle shape | 12 | -1.8433 bps | -22.1198 bps | failed |
| `research_v09_family_h120_oracle_shape_adaptive` | 120s | V08 H120 oracle shape | 7 | -6.1672 bps | -43.1707 bps | failed |

Conclusion: the V08 oracle shapes do not survive threshold adaptation from calibration-only windows.

## Calibrated-edge results

The calibrated-edge audit directly tested whether the long-window inverted-edge behavior can be learned from calibration rows.

| Run | Horizon | Calibrator | OOF trades | Mean net PnL | Total net PnL | Gate |
|---|---:|---|---:|---:|---:|---|
| `research_v09_calibrated_edge_h45_logistic` | 45s | logistic | 30 | -3.0076 bps | -90.2293 bps | failed |
| `research_v09_calibrated_edge_h60_logistic` | 60s | logistic | 14 | -1.2808 bps | -17.9308 bps | failed |
| `research_v09_calibrated_edge_h90_logistic` | 90s | logistic | 12 | -0.4343 bps | -5.2121 bps | failed |
| `research_v09_calibrated_edge_h90_ridge` | 90s | ridge | 15 | -0.1203 bps | -1.8038 bps | failed |
| `research_v09_calibrated_edge_h120_logistic` | 120s | logistic | 11 | +0.2398 bps | +2.6378 bps | failed |

Conclusion: calibration-only edge correction does not currently rescue the strategy.  The best calibrated version is near flat, still below promotion quality.

## Current status

```text
v08 full-hindsight oracle diagnostics: positive but invalid for deployment
v09 family-adaptive oracle-shape conversion: failed
v09 calibrated-edge conversion: failed
v09 prequential H90 template transfer: positive lead, failed promotion gate
v09 5-fold robustness check: failed
stable profit: not established
```

## Next research path

1. Acquire or generate multi-session L2 + trades data.  Single-session fold gymnastics is now the bottleneck.
2. Promote the V09 H90 template-transfer branch only if it remains positive across many independent days.
3. Add trades prints and execution-side diagnostics, especially whether winning signals align with aggressive trade flow.
4. Add sample-size gates that require at least 100 non-overlapping trades before treating any bps estimate as credible.
5. Treat V09 H90 as a research hypothesis, not as a trading system.
