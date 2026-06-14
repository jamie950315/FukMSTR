# Research V07 Results

V07 continued the leak-free long-window work from V06. The focus was 30 seconds and longer windows, with extra attention on 45 seconds because the 30/60/90/120 second leak-free baselines remained weak on the bundled Deribit sample.

## Main code changes

- Added `src/lob_microprice_lab/selective.py`.
  - Calibration-only selective filters for long-window model predictions.
  - Supports probability-edge thresholds, signed LOB agreement/disagreement filters, optional spread filters, optional volatility filters, and `normal`/`invert` direction modes.
  - Every numeric filter threshold is computed from a past calibration window before applying to validation.
  - Refuses any filter column starting with `future_`.
- Added `selective-from-ensemble` CLI.
  - Post-processes any existing `ensemble-walk-forward` run that has per-fold `calibration_predictions.csv` and `validation_predictions.csv`.
  - Produces per-fold candidate leaderboards, selected candidate JSON files, OOF selective backtest, fixed-signal stress, and shifted-signal null tests.
- Added shifted-signal null tests.
  - Circularly shifts selected raw signals relative to the price path.
  - Preserves signal frequency/clustering while destroying time alignment.
  - Reports how often shifted null signals beat the real selected signals.
- Added `tests/test_selective_v07.py`.
- Added `make selective-h45-v07`.

## Data and execution assumptions

All V07 experiments use the bundled single-day Deribit `BTC-PERPETUAL` L2 book sample:

```text
data/real_tardis/book_depth10_500ms.csv
```

Common setup:

```text
sampling: 500 ms
features: leak-free stationary-only unless stated otherwise
execution: taker bid/ask non-overlap
primary cost: 1.5 bps
primary latency: 0.5 seconds
stress grid: 1.5 / 3.0 / 5.0 bps x 0 / 0.5 / 1.0 / 2.0 seconds
folding: chronological walk-forward
```

## Baseline long-window sweep

V07 extended the leak-free stationary logistic baseline to 60, 90, and 120 seconds.

| Run | Horizon | OOF trades | Hit rate | Mean net bps | Total net bps | Gate |
|---|---:|---:|---:|---:|---:|---|
| v06 H30 baseline | 30s | 50 | 0.4800 | -0.1503 | -7.5140 | failed |
| v06 H45 baseline | 45s | 36 | 0.4444 | -0.9439 | -33.9818 | failed |
| v07 H60 baseline | 60s | 29 | 0.4828 | -0.8324 | -24.1390 | failed |
| v07 H90 baseline | 90s | 17 | 0.2941 | -2.0530 | -34.9009 | failed |
| v07 H120 baseline | 120s | 12 | 0.4167 | -0.9055 | -10.8662 | failed |

Result: extending the horizon alone did not recover profitability after the V06 leakage fix.

## Selective-filter research

The best V07 lead is a 45-second selective strategy with no spread/volatility filters, calibration-only edge/sign filters, and direction-mode search.

```text
run: runs/research_v07_selective_h45_invertgrid_nospread
source predictions: runs/research_v06_leakfree_stationary_logistic_h45_3fold_top80
horizon: 45s
edge thresholds: 0.2, 0.5, 0.7
signed columns: imbalance_l3, microprice_dev_bps_l3, mid_ret_60r_bps
spread filters: disabled
vol filters: disabled
direction modes: normal, invert
```

| Metric | Result |
|---|---:|
| OOF trades | 25 |
| OOF hit rate | 0.5200 |
| OOF mean net bps | 1.7714 |
| OOF total net bps | 44.2850 |
| Fold min trades | 6 |
| Fold min mean net bps | -0.0260 |
| Fold min bootstrap p05 bps | -3.4251 |
| Shift-null p(total >= actual) | 0.1000 |
| Shift-null p(mean >= actual) | 0.0500 |
| Strict selective pass | false |
| Robust profit gate | false |

Fold-level selected candidates:

| Fold | Direction | Filter | Trades | Hit rate | Mean net bps | Total net bps | Bootstrap p05 |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 | normal | `imbalance_l3` agree | 12 | 0.5833 | 3.3356 | 40.0273 | 0.1594 |
| 2 | invert | `microprice_dev_bps_l3` agree | 6 | 0.5000 | 0.7400 | 4.4398 | -2.8235 |
| 3 | invert | `imbalance_l3` agree | 7 | 0.4286 | -0.0260 | -0.1821 | -3.4251 |

Stress for the best V07 lead:

| Cost bps | Latency sec | Trades | Hit rate | Mean net bps | Total net bps |
|---:|---:|---:|---:|---:|---:|
| 1.5 | 0.0 | 25 | 0.64 | 2.3115 | 57.7866 |
| 1.5 | 0.5 | 25 | 0.52 | 1.7714 | 44.2850 |
| 1.5 | 1.0 | 25 | 0.52 | 1.5174 | 37.9341 |
| 1.5 | 2.0 | 25 | 0.52 | 1.4537 | 36.3421 |
| 3.0 | 0.0 | 25 | 0.56 | 0.8115 | 20.2866 |
| 3.0 | 0.5 | 25 | 0.48 | 0.2714 | 6.7850 |
| 3.0 | 1.0 | 25 | 0.48 | 0.0174 | 0.4341 |
| 3.0 | 2.0 | 25 | 0.48 | -0.0463 | -1.1579 |
| 5.0 | 0.0 | 25 | 0.48 | -1.1885 | -29.7134 |
| 5.0 | 0.5 | 25 | 0.48 | -1.7286 | -43.2150 |
| 5.0 | 1.0 | 25 | 0.48 | -1.9826 | -49.5659 |
| 5.0 | 2.0 | 25 | 0.48 | -2.0463 | -51.1579 |

Interpretation: the lead is positive under 1.5 bps and most 3.0 bps cases, but it fails at 3.0 bps / 2.0 seconds and fails every 5.0 bps case. It is still a research lead, not a stable-profit result.

## More stress-resistant but too sparse variant

```text
run: runs/research_v07_selective_h45_invertgrid_from_v06
```

This variant allowed spread filters. It produced stronger average PnL and remained positive through the 3.0 bps / 2.0 seconds stress cell, but one validation fold generated zero trades.

| Metric | Result |
|---|---:|
| OOF trades | 18 |
| OOF hit rate | 0.5556 |
| OOF mean net bps | 2.4704 |
| OOF total net bps | 44.4671 |
| Fold min trades | 0 |
| Fold min bootstrap p05 bps | -2.8235 |
| Shift-null p(total >= actual) | 0.0000 |
| Robust gate including 5 bps | failed |

Key stress rows:

| Cost bps | Latency sec | Mean net bps | Total net bps |
|---:|---:|---:|---:|
| 1.5 | 0.5 | 2.4704 | 44.4671 |
| 3.0 | 2.0 | 0.6613 | 11.9027 |
| 5.0 | 0.5 | -1.0296 | -18.5329 |

Interpretation: this is a promising sparse signal, but the zero-trade fold blocks promotion.

## Fixed-candidate stability audit

V07 also tested fixed candidate templates on the same H45 validation folds. These candidates did not use per-fold calibration-selected thresholds. All tested fixed candidates were negative.

| Candidate | OOF trades | Hit rate | Mean net bps | Total net bps |
|---|---:|---:|---:|---:|
| invert `microprice_dev_bps_l3` agree 0.8 | 21 | 0.4286 | -0.7856 | -16.4985 |
| normal `imbalance_l3` agree 0.0 | 33 | 0.4848 | -0.8452 | -27.8913 |
| invert `imbalance_l3` agree 0.0 | 26 | 0.4615 | -1.0426 | -27.1076 |
| normal `microprice_dev_bps_l3` agree 0.8 | 30 | 0.4667 | -2.3752 | -71.2550 |

Interpretation: the positive V07 H45 results depend on calibration-adaptive candidate selection. This raises overfitting risk and requires more days before promotion.

## V07 leaderboard

Full CSV:

```text
runs/research_v07_summary/leaderboard.csv
```

Top rows:

| Run | Horizon | OOF trades | Hit rate | Mean net bps | Total net bps | Strict pass |
|---|---:|---:|---:|---:|---:|---|
| h45 selective invert + spread | 45s | 18 | 0.5556 | 2.4704 | 44.4671 | false |
| h45 selective invert no-spread | 45s | 25 | 0.5200 | 1.7714 | 44.2850 | false |
| h45 selective limited | 45s | 29 | 0.5172 | 0.2833 | 8.2159 | false |
| h30 baseline | 30s | 50 | 0.4800 | -0.1503 | -7.5140 | false |
| h60 baseline | 60s | 29 | 0.4828 | -0.8324 | -24.1390 | false |

## Current conclusion

V07 found a better long-window research lead than V06: 45-second calibration-only selective filters can produce positive OOF net PnL on the bundled single-day sample, and the best H45 lead beats shifted-signal nulls at the 5% to 10% level.

The result still fails the stable-profit standard because trade count is small, bootstrap lower bounds remain negative, selected candidates vary across folds, fixed candidate templates lose money, 5 bps stress fails, and the evidence is still single-day only.

Current promotion status:

```text
single-day leak-free selective long-window lead: found
single-day strict profit gate: failed
multi-day stability gate: not tested
live deployment gate: failed by missing evidence
```

## Next research actions

1. Acquire multi-day L2 + trades data and rerun `selective-from-ensemble` on at least 20 independent days.
2. Promote only candidates that keep positive fold-level mean net PnL, positive bootstrap p05, and positive shifted-signal null rank across days.
3. Add a fixed-template promotion gate: adaptive selection can propose candidates, but a stable strategy needs a template that survives future days without frequent parameter changes.
4. Add trade-print features and funding/fee-tier assumptions before any live-style claim.
5. Treat H45 selective signals as the current best research branch; deprioritize 60/90/120s on this sample until more data is available.
