# Research V22 Results - BTC Rescue Profit Lock

V22 continues from V20/V21 and targets the remaining BTC contract weakness: V20 reached 100% selected-trade win rate, but it left one large winning long setup out and the full 10 bps-per-side / 5 sec stress corner was weak. V21 improved the exit target. V22 adds one slot-preserving long-only BTC rescue lane and raises the take-profit target to 52 bps.

## Frozen inputs

```text
User taker fee: 0.0400% per side = 4 bps per side
User maker fee: 0.0000% per side
Research route: taker entry + taker exit
Round-trip fee: 8 bps
Horizon: 90 seconds
Base latency: 0.5 seconds
Stop loss: disabled
Take profit: 52 bps
Reserve horizon slot: true
```

V19 high-fee filters remain:

```text
signal * kline_15s_signal >= -0.7266055861290821
kline_1m_rv_3_bps <= 17.890597279145457
kline_1m_range_z_6 >= -1.3068193253455331
```

V20 BTC side guard remains:

```text
if direction is long: require kline_15s_signal <= 0.0
if direction is short: no extra side guard
```

V22 adds one rescue lane:

```text
if direction is long:
    allow rescue when kline_15s_signal <= -0.70 and kline_1m_rv_3_bps >= 20.0
```

This is slot-preserving. It can only re-enable a pre-existing frozen V17 slot; it does not create replacement overlapping trades.

## V22 aggregate result

Run:

```text
runs/research_v22_btc_rescue_profit_lock_tp52
```

| Metric | V22 |
|---|---:|
| Gate passed | true |
| Trades | 11 |
| Win rate | 100.00% |
| Mean net PnL | +16.7050 bps/trade |
| Median net PnL | +11.0446 bps/trade |
| Total net PnL | +183.7545 bps |
| Profit factor | inf |
| Max drawdown | 0.0000 bps |
| Take-profit exits | 2 |
| Horizon exits | 9 |
| Worst fold total | +6.9553 bps |
| Worst fold mean | +3.4776 bps/trade |
| Bootstrap mean p05 | +6.7019 bps/trade |
| Bootstrap total p05 | +73.7207 bps |
| 5 equal-trade blocks positive | 5 / 5 |
| 10 equal-trade blocks positive | 10 / 10 |
| Leave-one-trade-out minimum total | +138.3084 bps |
| Leave-one-fold-out minimum total | +81.9835 bps |
| Remove top 5 winners total | +23.3427 bps |
| Remove top 7 winners total | +7.6269 bps |

## Comparison

| Metric | V20 side guard TP40 | V21 TP45 | V22 rescue TP52 |
|---|---:|---:|---:|
| Trades | 10 | 10 | 11 |
| Win rate | 100.00% | 100.00% | 100.00% |
| Mean net PnL | +12.8764 | +13.4332 | +16.7050 |
| Total net PnL | +128.7639 | +134.3322 | +183.7545 |
| Max drawdown | 0.0000 | 0.0000 | 0.0000 |
| Minimum trade | +0.7219 | +0.7219 | +0.7219 |

## Fold metrics

| Fold | Trades | Win rate | Mean net PnL | Total net PnL |
|---:|---:|---:|---:|---:|
| 1 | 3 | 100.00% | +33.9237 | +101.7710 |
| 2 | 2 | 100.00% | +19.8380 | +39.6761 |
| 3 | 2 | 100.00% | +11.3811 | +22.7622 |
| 4 | 2 | 100.00% | +3.4776 | +6.9553 |
| 5 | 2 | 100.00% | +6.2950 | +12.5899 |

## Fee and latency stress

Stress grid:

```text
taker fee per side: 4, 5, 6, 7.5, 10 bps
latency: 0, 0.5, 1, 2, 3, 5 sec
cells: 30
```

All cells passed:

```text
stress_all_cells_positive = true
worst total = +22.3729 bps
worst mean = +2.0339 bps/trade
```

This improves the V20 extreme corner, which was slightly negative at 10 bps per side and 5 sec latency.

## Family-wise shifted null

V22 audits a combined entry and exit family:

```text
side candidate count: 8
rescue candidate count: 17
exit target candidate count: 13
total candidate count: 1768
shift-null runs: 1000
```

| Null check | Add-one p(total) | Add-one p(mean) | Null max total | Null max mean |
|---|---:|---:|---:|---:|
| Selected-only | 0.000999 | 0.000999 | +7.2670 | +0.6606 |
| Full entry/exit family | 0.000999 | 0.000999 | +41.0120 | +3.7284 |

## Missed trade and extra cost checks

| Check | Result |
|---|---:|
| 50% missed-trade p05 total | +22.6323 bps |
| 50% missed-trade positive rate | 99.96% |
| Extra +16 bps per trade total | +7.7545 bps |

## Leverage scenarios

Approximate account-return scenarios, no compounding:

| Leverage | Approx total account return | Approx liquidation buffer before safety shock |
|---:|---:|---:|
| 1x | +1.8375% | 9942.0 bps |
| 2x | +3.6751% | 4942.0 bps |
| 3x | +5.5126% | 3275.3 bps |
| 5x | +9.1877% | 1942.0 bps |
| 10x | +18.3754% | 942.0 bps |
| 20x | +36.7509% | 442.0 bps |

Promoted leverage cap remains 3x because this is still a bundled-sample result. Higher leverage is simulation-only until independent BTC contract validation passes.

## Added files

```text
src/lob_microprice_lab/btc_rescue_profit_lock.py
scripts/run_btc_rescue_profit_lock_v22.py
tests/test_btc_rescue_profit_lock_v22.py
docs/RESEARCH_V22_COMMANDS.md
reports/RESEARCH_V22_RESULTS.md
runs/research_v22_btc_rescue_profit_lock_tp52/
```

## Status

```text
V20 BTC side guard reproduced: yes
V21 profit target path extended: yes
V22 rescue lane added: yes
Real-fee taker/taker assumption: 8 bps round trip
Bundled-sample win rate: 100.00%
Full 10 bps/side and 5 sec stress grid: passed
Entry/exit family shifted null: passed
Promoted leverage cap: 3x research-only
Independent multi-day BTC validation: still required
Live stable profit: not yet proven
```

## Caveat

V22 is the strongest bundled-sample BTC contract rule so far, but it still must be frozen and tested on independent multi-day BTCUSDT contract data. Do not keep tuning thresholds on the same bundled sample.
