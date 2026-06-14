# Research V24 Results: BTC Adaptive Exit + Safety Lock

V24 continues from V22/V23 and keeps the BTC entry rule frozen. It improves the system by changing only the reserved-slot exit behavior and then adding an account-level safety certificate.

## Main runs

```text
runs/research_v24_btc_adaptive_exit_lock
runs/research_v24_btc_adaptive_exit_safety_lock
```

## Frozen assumptions

```text
Taker fee: 0.0400% per side = 4 bps per side
Maker fee: 0.0000% per side
Promoted route: taker entry + taker exit = 8 bps round trip
Horizon: 90 sec
Latency: 0.5 sec
Stop loss: disabled
Reserve horizon slot: true
```

## What changed from V22

V22 used a fixed 52 bps take-profit target. V24 keeps the same V22 entry slots and applies an adaptive take-profit ladder:

```text
Long default take profit: 52 bps
Short default take profit: 45 bps
Short compression: if kline_15s_signal >= 0.45, take profit = 25 bps
Soft long compression: if prob_edge <= 0.20 and kline_15s_signal <= -0.40, take profit = 20 bps
```

The exit remains slot-preserving. Early take-profit does not open a new overlapping trade opportunity.

## Trade-level result

| Metric | V22 fixed TP52 | V24 adaptive exit |
|---|---:|---:|
| Trades | 11 | 11 |
| Selected-trade win rate | 100.00% | 100.00% |
| Mean net PnL | +16.7050 bps | +17.2816 bps |
| Median net PnL | +11.0446 bps | +14.2522 bps |
| Total net PnL | +183.7545 bps | +190.0977 bps |
| Max drawdown | 0.0000 bps | 0.0000 bps |
| Take-profit exits | 2 | 5 |
| Horizon exits | 9 | 6 |
| Mean hold time | 84.3507 sec | 78.6237 sec |
| Worst trade | +0.7219 bps | +0.7219 bps |

## Fold result

| Fold | Trades | Win rate | Mean net PnL | Total net PnL |
|---:|---:|---:|---:|---:|
| 1 | 3 | 100.00% | +35.2434 | +105.7301 |
| 2 | 2 | 100.00% | +19.8380 | +39.6761 |
| 3 | 2 | 100.00% | +11.3811 | +22.7622 |
| 4 | 2 | 100.00% | +3.4776 | +6.9553 |
| 5 | 2 | 100.00% | +7.4870 | +14.9741 |

## Robustness checks

| Check | Result |
|---|---:|
| Gate passed | true |
| Bootstrap mean p05 | +7.3521 bps/trade |
| Bootstrap total p05 | +80.8732 bps |
| 5 equal-trade blocks positive | 5 / 5 |
| 10 equal-trade blocks positive | 10 / 10 |
| Leave-one-trade-out minimum total | +144.6517 bps |
| Leave-one-fold-out minimum total | +84.3676 bps |
| Remove top 5 winners total | +26.5504 bps |
| Remove top 7 winners total | +7.6269 bps |
| 50% missed-trade p05 total | +25.8391 bps |
| 50% missed-trade positive rate | 99.94% |
| Extra +16 bps per trade total | +14.0977 bps |

## Fee and latency stress

Stress grid:

```text
taker fee per side: 4, 5, 6, 7.5, 10 bps
latency: 0, 0.5, 1, 2, 3, 5 sec
```

| Stress item | Result |
|---|---:|
| All 30 cells positive | true |
| Worst stress total | +39.7487 bps |
| Worst stress mean | +3.6135 bps/trade |
| 10 bps/side + 5 sec total | +44.6552 bps |

## Adaptive-exit family correction

| Item | Result |
|---|---:|
| Adaptive-exit candidates audited | 47 |
| Predeclared full entry/exit candidate count | 6,392 |
| Shift-null runs | 1,000 |
| Selected-only add-one p(total) | 0.000999 |
| Selected-only add-one p(mean) | 0.000999 |
| Adaptive-exit family add-one p(total) | 0.000999 |
| Adaptive-exit family add-one p(mean) | 0.000999 |

The V22 entry and rescue rules remain frozen. V24 retests only the adaptive exit layer on top of the existing frozen BTC entry policy.

## Account-level safety certificate

V24 also applies the adaptive safety governor:

```text
Normal leverage: 5x research-only
Risk-off leverage: 4x
Risk-off trigger: realized trade <= -20 bps notional
Risk-off duration: next 3 trades
```

| Account-level item | Result |
|---|---:|
| Gate passed | true |
| No-loss account return, no compounding | +9.5049% |
| Extreme 10 bps/side + 5 sec account return | +2.2328% |
| 50% missed-trade p05 account return | +1.2894% |
| Extra +16 bps/trade account return | +0.7049% |
| Synthetic -40 bps losses injected | 3 |
| Synthetic-loss minimum account return | +1.6186% |
| Synthetic-loss worst drawdown | -4.9218% |

The 5x cap is research-only and depends on the bundled sample, simplified liquidation buffer, and synthetic loss stress. It must not be treated as live sizing advice.

## Status

```text
V24 trade-level bundled-sample target: passed
V24 account-level safety target: passed
Selected-trade win rate on bundled sample: 100.00%
Full severe fee/latency stress: passed
Independent multi-day BTCUSDT validation: still required
Live stable profit: not yet proven
```
