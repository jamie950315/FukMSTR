# Research V19 Results - Real-Fee Profit Lock

V19 starts from the frozen V17/V18 policy and uses the user-supplied real fee schedule:

```text
taker fee: 0.0400% = 4 bps per side
maker fee: 0.0000% = 0 bps per side
full taker round trip: 8 bps
```

The old V17 result used 1.5 bps total test cost. Under the user's taker/taker fee, the frozen V17 ledger still makes money, but the fold stability and win rate weaken. V19 therefore adds a slot-preserving high-fee guard. It does not add extra overlapping trades.

## V17 repriced with the real taker fee

| Metric | V17 repriced |
|---|---:|
| Trades | 20 |
| Hit rate | 55.00% |
| Mean net PnL | +3.6404 bps/trade |
| Total net PnL | +72.8090 bps |
| Worst fold total | -9.9416 bps |
| Worst fold mean | -1.9883 bps/trade |

Conclusion: V17 remains positive overall under an 8 bps taker/taker round trip, but it no longer satisfies the desired stability standard because some folds turn negative.

## V19 promoted high-fee guard

V19 keeps the V17 entry/exit logic and adds these fixed filters:

```text
signal * kline_15s_signal >= -0.7266055861290821
kline_1m_rv_3_bps <= 17.890597279145457
kline_1m_range_z_6 >= -1.3068193253455331
```

The selected route is still taker entry plus taker exit. Maker fee is recorded as zero, but the package does not promote a maker route because reliable maker fills require queue/fill data that is not present in the bundled sample.

## V19 result under the user's real taker fee

| Metric | V19 |
|---|---:|
| Gate passed | true |
| Trades | 11 |
| Hit rate | 90.91% |
| Mean net PnL | +11.0505 bps/trade |
| Median net PnL | +4.6713 bps/trade |
| Total net PnL | +121.5554 bps |
| Profit factor | 17.8628 |
| Max drawdown | -7.2085 bps |
| Worst fold mean | +3.4776 bps/trade |
| Worst fold total | +6.9553 bps |
| Bootstrap mean p05 | +5.1229 bps/trade |
| Bootstrap total p05 | +56.3516 bps |
| 5 equal-trade blocks positive | 5 / 5 |
| 5-block min total | +6.9553 bps |
| Leave-one-trade-out min total | +80.2512 bps |
| Leave-one-fold-out min total | +69.2066 bps |

## Fold results

| Fold | Trades | Hit rate | Mean net PnL | Total net PnL |
|---:|---:|---:|---:|---:|
| 1 | 2 | 100.00% | +26.1744 | +52.3488 |
| 2 | 2 | 100.00% | +17.0538 | +34.1077 |
| 3 | 3 | 66.67% | +5.1846 | +15.5537 |
| 4 | 2 | 100.00% | +3.4776 | +6.9553 |
| 5 | 2 | 100.00% | +6.2950 | +12.5899 |

## Fee and latency stress

Stress grid:

```text
taker fee per side = 4, 5, 6, 7.5, 10 bps
latency = 0, 0.5, 1, 2, 3, 5 sec
```

Gate region passed:

```text
taker fee per side <= 7.5 bps
latency <= 5 sec
minimum mean = +3.1885 bps/trade
minimum total = +35.0731 bps
```

Extreme warning:

```text
taker fee per side = 10 bps
latency = 5 sec
total = -19.9269 bps
mean = -1.8115 bps/trade
```

So V19 is positive through a large buffer above the user's 4 bps taker fee, but it is not positive at 10 bps per side with 5 sec delay.

## Shift-null and family correction

| Check | Result |
|---|---:|
| Shift-null runs | 1000 |
| Selected-only add-one p(total) | 0.000999 |
| Selected-only add-one p(mean) | 0.000999 |
| Fee-filter family candidates | 213 |
| Fee-family add-one p(total) | 0.000999 |
| Fee-family constrained add-one p(mean) | 0.000999 |

Unconstrained family mean p-value is 0.0769 because tiny low-trade shifted candidates can have high average PnL. The gate uses constrained family mean, requiring at least the selected minimum trade count before comparing mean PnL.

## Deployment-style stress

| Check | Result |
|---|---:|
| 50% missed-trade p05 total | +11.5763 bps |
| 50% missed-trade positive scenario rate | 99.08% |
| Extra +10 bps per trade total | +11.5554 bps |

## Status

```text
V19 real-fee research gate: passed
V19 hit-rate target under user fee: passed
V19 fold stability under user fee: passed
V19 stress through 7.5 bps taker/side and 5 sec latency: passed
V19 shifted family correction: passed under constrained trade-count comparison
true independent multi-day stable profit: not established
live trading readiness: not established
```

The next real upgrade is to run the frozen V19 rule on new multi-day data without changing the three thresholds.
