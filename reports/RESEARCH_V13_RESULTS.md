# Research V13 Results: Multi-timeframe K-line Data Added on Top of Uploaded V12

## Objective

The user supplied the v12 zip and asked to continue from the exact v12 state, then add K-line / candlestick graph data into training data and weighting to improve prediction accuracy and profit stability.

V13 preserves the v12 H90 slot-preserving OFI veto as the baseline and adds:

```text
src/lob_microprice_lab/kline_features.py
src/lob_microprice_lab/kline_weighting.py
src/lob_microprice_lab/kline_blend.py
tests/test_kline_features_v13.py
tests/test_kline_weighting_v13.py
docs/KLINE_DATA_SCHEMA.md
docs/RESEARCH_V13_COMMANDS.md
runs/research_v13_summary.csv
runs/research_v13_alpha_blend_scan.csv
```

New CLI commands:

```text
build-kline-cache
kline-weight-audit
kline-blend-ensemble
```

The existing `ensemble-walk-forward` command now also accepts:

```text
--kline-timeframes
--kline-candle
--kline-decision-lag-sec
--kline-lookbacks
```

## Baseline: uploaded V12 status

The original v12 lead remains the reference benchmark.

```text
run: runs/research_v12_slot_veto_h90_ofi_l5_q90
source ensemble: runs/research_v09_ensemble_h90_5fold_stationary
horizon: 90s
base edge threshold: 0.1
veto: ofi_sum_l5_norm <= fold calibration q0.9
execution: taker bid/ask, non-overlap
latency: 0.5s
cost: 1.5 bps
gate: passed
```

| Metric | V12 result |
|---|---:|
| Trades | 21 |
| Hit rate | 52.38% |
| Mean net PnL | +7.1647 bps/trade |
| Total net PnL | +150.4583 bps |
| Worst fold mean | +4.5117 bps/trade |
| Worst fold total | +16.8734 bps |
| Bootstrap mean p05 | +2.3167 bps/trade |
| Stress min mean | +3.5125 bps/trade |
| Stress min total | +73.7624 bps |
| Shift-null p(total) | 0.0000 |
| Shift-null p(mean) | 0.0000 |
| OFI-family p(total) | 0.0000 |
| OFI-family p(mean) | 0.0875 |

## K-line feature construction

V13 created closed-candle features over:

```text
1s, 5s, 15s, 1m, 5m, 15m
```

with lookbacks:

```text
1, 3, 6, 12
```

The main K-line feature audit reported:

```text
rows: 10000
K-line feature columns: 252
leakage audit ok: true
max_overrun_ns: 0
```

Missing rate by timeframe:

| Timeframe | Missing rate |
|---|---:|
| 1s | 0.02% |
| 5s | 0.10% |
| 15s | 0.29% |
| 1m | 1.18% |
| 5m | 5.88% |
| 15m | 17.62% |

The missing rate is expected at the beginning of the sample because longer timeframes require closed historical bars before they can produce features.

## Experiment A: direct K-line retraining

This experiment appended K-line features to the LOB model and retrained the H90 ensemble on the same v12 fold schedule.

```text
run: runs/research_v13_kline_h90_5fold_stationary_v12folds
gate: failed
```

| Metric | Result |
|---|---:|
| OOF trades | 25 |
| Hit rate | 44.00% |
| Mean net PnL | +1.0457 bps/trade |
| Total net PnL | +26.1413 bps |
| Worst fold mean | -8.9380 bps/trade |
| Worst fold total | -44.6901 bps |
| Worst fold bootstrap p05 | -18.3263 bps/trade |
| Stress min mean | -1.3956 bps/trade |
| Stress min total | -36.2848 bps |

Fold results:

| Fold | Trades | Hit rate | Mean net PnL | Total net PnL |
|---:|---:|---:|---:|---:|
| 1 | 5 | 20.00% | -8.9380 | -44.6901 |
| 2 | 5 | 60.00% | +8.9994 | +44.9968 |
| 3 | 5 | 40.00% | +2.2982 | +11.4910 |
| 4 | 5 | 60.00% | +4.5210 | +22.6050 |
| 5 | 5 | 40.00% | -1.6523 | -8.2614 |

Conclusion: directly adding K-line columns to the training matrix improved feature richness but did not improve stability. It failed the fold, bootstrap, and stress requirements.

## Experiment B: calibration-only K-line weight search

This experiment searched calibration-only weights over the base probability edge and K-line per-timeframe signals, then applied the selected weights to validation.

```text
run: runs/research_v13_kline_weight_h90_v12folds
gate: failed
candidate count per fold: 365
```

| Metric | Result |
|---|---:|
| OOF trades | 20 |
| Hit rate | 50.00% |
| Mean net PnL | +1.2443 bps/trade |
| Total net PnL | +24.8869 bps |
| Worst fold mean | -10.0763 bps/trade |
| Worst fold total | -50.3814 bps |
| Bootstrap mean p05 | -4.8770 bps/trade |
| Stress min mean | -2.4937 bps/trade |
| Stress min total | -49.8742 bps |
| Shift-null p(total) | 0.0732 |
| Shift-null p(mean) | 0.0732 |

Conclusion: calibration-only weight optimization was still too flexible for the single-day sample and failed fold/bootstrap/stress gates. It should not be promoted.

## Experiment C: fixed 10% K-line probability blend plus v12 OFI slot-veto

The successful V13 candidate is deliberately conservative: keep the original v12 model as the main signal and add only a fixed 10% K-line-trained model overlay.

```text
blended_prob = 0.90 * v12_prob + 0.10 * kline_model_prob
```

Then the original v12 slot-preserving OFI veto is applied unchanged.

```text
run: runs/research_v13_slot_veto_kline_blend_alpha010_h90
gate: passed
```

| Metric | V12 baseline | V13 fixed K-line blend |
|---|---:|---:|
| Trades | 21 | 23 |
| Hit rate | 52.38% | 52.17% |
| Mean net PnL | +7.1647 | +6.5838 |
| Total net PnL | +150.4583 | +151.4272 |
| Worst fold mean | +4.5117 | +2.2604 |
| Worst fold total | +16.8734 | +9.0417 |
| Bootstrap mean p05 | +2.3167 | +2.4937 |
| Stress min mean | +3.5125 | +2.8068 |
| Stress min total | +73.7624 | +64.5565 |
| Shift-null p(total) | 0.0000 | 0.0000 |
| Shift-null p(mean) | 0.0000 | 0.0000 |
| OFI-family p(total) | 0.0000 | 0.0000 |
| OFI-family p(mean) | 0.0875 | 0.0375 |

Fold results:

| Fold | Trades | Hit rate | Mean net PnL | Total net PnL |
|---:|---:|---:|---:|---:|
| 1 | 5 | 60.00% | +12.9923 | +64.9617 |
| 2 | 5 | 60.00% | +7.2483 | +36.2415 |
| 3 | 5 | 40.00% | +4.5117 | +22.5584 |
| 4 | 4 | 50.00% | +2.2604 | +9.0417 |
| 5 | 4 | 50.00% | +4.6560 | +18.6239 |

Stress test:

```text
stress cells: 12
positive mean cells: 12
positive total cells: 12
min trades: 23
min mean net PnL: +2.8068 bps/trade
min total net PnL: +64.5565 bps
```

Null controls:

```text
shift-null p(total): 0.0000
shift-null p(mean): 0.0000
OFI-family candidate count: 15
OFI-family p(total): 0.0000
OFI-family p(mean): 0.0375
constrained OFI-family p(total): 0.0000
constrained OFI-family p(mean): 0.0000
```

## Alpha diagnostic scan

The fixed-alpha scan was written to:

```text
runs/research_v13_alpha_blend_scan.csv
```

| K-line alpha | Trades | Mean net PnL | Total net PnL | Worst fold mean |
|---:|---:|---:|---:|---:|
| 0.00 | 21 | +7.1647 | +150.4583 | +4.5117 |
| 0.05 | 23 | +6.1359 | +141.1267 | +2.2604 |
| 0.10 | 23 | +6.5838 | +151.4272 | +2.2604 |
| 0.15 | 23 | +6.5838 | +151.4272 | +2.2604 |
| 0.20 | 24 | +3.9055 | +93.7331 | -6.7322 |
| 0.25 | 23 | +5.6903 | +130.8771 | -0.1016 |
| 0.30 | 22 | +2.2926 | +50.4373 | -3.6714 |
| 0.40 | 22 | +3.1336 | +68.9385 | -4.6739 |
| 0.50 | 23 | -0.0417 | -0.9590 | -8.9380 |
| 0.75 | 24 | +0.4914 | +11.7942 | -8.9380 |
| 1.00 | 24 | +1.6809 | +40.3417 | -8.9380 |

Interpretation: the K-line model should be a small overlay, not a replacement for the v12 microstructure signal. Higher K-line weights degrade fold stability.

## V13 conclusion

V13 did start from the uploaded v12 state and preserved the v12 gate-passing baseline. Adding K-line features directly to training did not improve the strict gate, and calibration-only weight optimization was unstable. The best single-day result is a small fixed 10% K-line probability overlay plus the original v12 OFI slot-preserving veto.

Status:

```text
uploaded v12 baseline reproduced: yes
multi-timeframe K-line feature pipeline: added
leakage-safe K-line alignment: audit passed
direct K-line retraining: failed strict gate
K-line weight search: failed strict gate
fixed 10% K-line overlay + v12 OFI veto: single-day gate passed
stable profit: not established
live deployment gate: not established
```

Important caveat: V13 includes the same shifted-signal and OFI-family correction used in v12, but it does not yet fully correct for K-line alpha-family selection. The alpha scan should be treated as diagnostic. The next promotion step must lock alpha and all K-line timeframes before running multi-day validation.

## Recommended V14 promotion gate

Before considering this stable, run the fixed V13 candidate on at least:

```text
20+ independent trading days
100+ non-overlap trades
fixed alpha=0.10 selected before validation
fixed K-line timeframes and lookbacks selected before validation
session-level PnL positive after costs
worst fold/session mean PnL positive
aggregate bootstrap p05 positive
shift-null p(total) <= 0.05 and p(mean) <= 0.05
combined OFI + K-line family-wise correction p <= 0.05
stress test positive at 5 bps cost and 2s latency
```
