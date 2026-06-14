# Research V14 Results: K-line Stability Lock

## Objective

The user asked to continue research and not stop until stable-profit success.  V14 continues from the uploaded v12 baseline and the v13 K-line overlay, but it does not simply optimize validation PnL.  The main V14 change is a stricter stability-lock audit that closes the v13 alpha-selection caveat.

The V14 selected policy is:

```text
base model: v12/v09 H90 ensemble
K-line model: v13 multi-timeframe K-line H90 ensemble
blend: 87.5% base probability + 12.5% K-line probability
edge threshold: 0.1
veto: slot-preserving ofi_sum_l5_norm <= fold calibration q0.9
horizon: 90s
execution: taker bid/ask, non-overlap
latency: 0.5s
cost: 1.5 bps
```

## New V14 code

```text
src/lob_microprice_lab/profit_stability.py
tests/test_profit_stability_v14.py
```

New CLI:

```text
kline-stability-lock-audit
```

New Make target:

```text
make kline-stability-lock-v14
```

New result files:

```text
runs/research_v14_kline_stability_lock_alpha0125_h90/summary.json
runs/research_v14_kline_stability_lock_alpha0125_h90/REPORT.md
runs/research_v14_kline_stability_lock_alpha0125_h90/alpha_ofi_family_candidates.csv
runs/research_v14_kline_stability_lock_alpha0125_h90/alpha_ofi_family_shift_null.csv
runs/research_v14_kline_stability_lock_alpha0125_h90/selected_shift_null.csv
runs/research_v14_summary.csv
```

## Why V14 is stricter than V13

V13 found that a fixed 10% K-line overlay passed the single-day v12 gate, but alpha-family correction was still not fully established.  V14 adds:

```text
selected-only shifted-signal null
alpha-family shifted-signal null over alpha = 0, 0.025, 0.05, 0.075, 0.10, 0.125, 0.15
OFI-family shifted-signal null over 3 OFI depths x 5 quantiles
union alpha/OFI shifted-signal null
6 chronological equal-trade block stability
leave-one-fold-out stability
stricter family p-value threshold <= 0.05 for both total and mean PnL
```

## Main V14 result

```text
run: runs/research_v14_kline_stability_lock_alpha0125_h90
gate: passed
```

| Metric | V14 result |
|---|---:|
| Trades | 23 |
| Hit rate | 56.52% |
| Mean net PnL | +7.4131 bps/trade |
| Total net PnL | +170.5013 bps |
| Worst fold mean | +2.2604 bps/trade |
| Worst fold total | +9.0417 bps |
| Bootstrap mean p05 | +3.1505 bps/trade |
| Bootstrap total p05 | +72.4613 bps |
| Stress min mean | +3.6705 bps/trade |
| Stress min total | +84.4221 bps |
| Selected shift-null p(total) | 0.0000 |
| Selected shift-null p(mean) | 0.0000 |
| Alpha-family p(total) | 0.0000 |
| Alpha-family p(mean) | 0.0000 |
| OFI-family p(total) | 0.0000 |
| OFI-family p(mean) | 0.0250 |
| Union alpha/OFI p(total) | 0.0000 |
| Union alpha/OFI p(mean) | 0.0250 |

## Comparison with V12 and V13

| Metric | V12 OFI slot-veto | V13 alpha=0.10 K-line blend | V14 alpha=0.125 stability lock |
|---|---:|---:|---:|
| Gate passed | true | true | true |
| Trades | 21 | 23 | 23 |
| Hit rate | 52.38% | 52.17% | 56.52% |
| Mean net PnL | +7.1647 | +6.5838 | +7.4131 |
| Total net PnL | +150.4583 | +151.4272 | +170.5013 |
| Worst fold mean | +4.5117 | +2.2604 | +2.2604 |
| Worst fold total | +16.8734 | +9.0417 | +9.0417 |
| Bootstrap mean p05 | +2.3167 | +2.4937 | +3.1505 |
| Stress min mean | +3.5125 | +2.8068 | +3.6705 |
| Stress min total | +73.7624 | +64.5565 | +84.4221 |
| OFI-family p(mean) | 0.0875 | 0.0375 | 0.0250 |
| Alpha-family p(mean) | not tested | not tested | 0.0000 |
| Union alpha/OFI p(mean) | not tested | not tested | 0.0250 |

V14 improves the v13 overlay on hit rate, mean PnL, total PnL, bootstrap p05, stress minimum, and family-corrected mean p-value.  It also introduces an explicit alpha-family correction, which was the main v13 caveat.

## Fold results

| Fold | Trades | Hit rate | Mean net PnL | Total net PnL |
|---:|---:|---:|---:|---:|
| 1 | 5 | 60.00% | +12.9923 | +64.9617 |
| 2 | 5 | 80.00% | +11.0631 | +55.3155 |
| 3 | 5 | 40.00% | +4.5117 | +22.5584 |
| 4 | 4 | 50.00% | +2.2604 | +9.0417 |
| 5 | 4 | 50.00% | +4.6560 | +18.6239 |

## Chronological equal-trade stability blocks

| Block | Trades | Mean net PnL | Total net PnL |
|---:|---:|---:|---:|
| 1 | 4 | +11.8543 | +47.4171 |
| 2 | 4 | +6.4399 | +25.7597 |
| 3 | 4 | +9.4424 | +37.7695 |
| 4 | 4 | +6.0144 | +24.0577 |
| 5 | 4 | +8.8104 | +35.2414 |
| 6 | 3 | +0.0853 | +0.2558 |

All six chronological equal-trade blocks are positive.  The last block is only barely positive, so it should be treated as a warning sign for multi-day validation rather than as a reason to deploy live.

## Family null controls

The selected alpha is tested against three families:

```text
alpha_fixed_filter: 7 alpha candidates with OFI l5 q0.9 fixed
ofi_selected_alpha: 15 OFI candidates with alpha fixed at 0.125
union_alpha_or_ofi: all 21 candidates in the alpha/OFI union family
```

| Family | Candidates | p(total) | p(mean) | Null total p95 | Null mean p95 |
|---|---:|---:|---:|---:|---:|
| selected only | 1 | 0.0000 | 0.0000 | +36.6423 | +1.9285 |
| alpha fixed filter | 7 | 0.0000 | 0.0000 | +72.1193 | +3.7958 |
| OFI selected alpha | 15 | 0.0000 | 0.0250 | +70.7663 | +5.9162 |
| union alpha/OFI | 21 | 0.0000 | 0.0250 | +87.7262 | +6.4251 |

## Current status

```text
uploaded v12 baseline reproduced: yes
v13 K-line training/weighting continued from v12: yes
v14 fixed K-line alpha stability lock: passed
alpha-family correction: passed
OFI-family correction: passed
union alpha/OFI correction: passed
single-sample research stability gate: passed
true multi-day stable profit: not yet established
live deployment gate: not established
```

## Important caveat

V14 is the strongest result in this project so far, but it is still based on the bundled single Deribit BTC-PERPETUAL L2 sample.  It should be described as **single-sample research stability success**, not proven live stable profit.  The next non-negotiable step is to freeze the V14 policy and validate it on independent multi-day data without changing alpha, OFI quantile, horizon, or edge threshold.
