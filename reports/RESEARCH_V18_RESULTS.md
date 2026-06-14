# Research V18 results: deployment-lock certificate

## Plain status

The project now has a saved rule that did well on the built-in sample. V17 decided when to enter and added a take-profit rule. V18 keeps those choices unchanged and checks whether the saved result still looks usable if live trading is messy: some orders are missed, fees are worse, and the sample is sliced into smaller clock-time chunks.

This is stronger than V17 as a readiness check, but it still does not prove real multi-day stable profit. For that, the same frozen rule must be run on new days that were not used during research.

## V18 policy status

V18 does not change the V17 trading policy.

```text
entry rule: frozen from V15/V16/V17
K-line overlay alpha: 0.125
OFI guard: ofi_sum_l5_norm <= calibration q0.9
K-line support guard: directional signal * kline_15s_rv_6_bps >= calibration q0.0
take profit: 40 bps
stop loss: disabled
slot reservation: enabled
horizon: 90 seconds
base cost: 1.5 bps
base latency: 0.5 seconds
```

## Main result

Run:

```text
runs/research_v18_deployment_lock_certificate
```

| Metric | Value |
|---|---:|
| Gate passed | true |
| Trades | 20 |
| Hit rate | 65.00% |
| Mean net PnL | +10.1404 bps/trade |
| Total net PnL | +202.8090 bps |
| Max drawdown | -12.6208 bps |
| V17 severe stress all positive | true |
| Severe-stress worst total | +9.8225 bps |
| Severe-stress worst mean | +0.4911 bps/trade |

## New V18 checks

### 1. Clock-time stability

V18 splits the saved sample by clock time instead of only by fold or equal number of trades.

| Clock blocks | Blocks with trades | Positive blocks | Worst block total |
|---:|---:|---:|---:|
| 3 | 3 | 3 | +19.4765 |
| 4 | 4 | 4 | +20.1239 |
| 5 | 5 | 5 | +16.8734 |
| 6 | 6 | 6 | +1.0474 |
| 8 | 8 | 8 | +0.9724 |
| 10 | 10 | 10 | +1.0474 |
| 12 | 10 | 9 | -3.0819 |

Gate uses the 10-block check, which passed.

### 2. Missed-trade stress

This simulates randomly missing trades. At the strict 50% missed-trade setting:

| Setting | Result |
|---|---:|
| Miss probability | 50% |
| Scenarios | 10,000 |
| 1% lower total | +3.8741 bps |
| 5% lower total | +28.2616 bps |
| Positive scenario rate | 99.40% |

### 3. Extra-cost reserve

This subtracts extra cost from every trade on top of the saved V17 result.

| Extra cost per trade | Total PnL |
|---:|---:|
| +0 bps | +202.8090 |
| +1 bps | +182.8090 |
| +2 bps | +162.8090 |
| +3 bps | +142.8090 |
| +5 bps | +102.8090 |
| +7.5 bps | +52.8090 |
| +10 bps | +2.8090 |

The aggregate result stays positive through +10 bps extra per trade. The weakest fold turns negative above moderate extra cost, so this should be read as an aggregate reserve, not a claim that every sub-period survives that much extra cost.

### 4. Combined failure stress

This simulates missing trades and extra cost together. The gate uses 50% missed trades plus +3 bps extra cost on kept trades.

| Setting | Result |
|---|---:|
| Miss probability | 50% |
| Extra cost on kept trades | +3 bps |
| Scenarios | 10,000 |
| 5% lower total | +5.1266 bps |
| 1% lower total | -17.9851 bps |
| Positive scenario rate | 96.39% |

The 5% lower bound is positive, so the V18 combined-failure gate passes. The 1% lower bound is negative, which is a warning that extreme unlucky missed-fill patterns can still lose.

## Gate result

All V18 gate checks passed:

```text
enough trades: passed
positive total: passed
positive mean: passed
V17 gate already passed: passed
trade ledger integrity: passed
severe stress positive: passed
10 clock-time blocks positive: passed
50% missed-trade 1% lower bound positive: passed
50% missed-trade 5% lower bound positive: passed
+10 bps extra-cost aggregate reserve positive: passed
50% missed + 3 bps extra-cost 5% lower bound positive: passed
```

## Caveat

V18 reaches a stronger single-sample deployment-readiness target. It still cannot honestly be called proven stable live profit because the zip contains only one bundled market sample. The next target is fixed-rule validation on independent multi-day data.
