# Research V20 Results - BTC Contract Leverage Lock

V20 continues from V19 real-fee lock and specializes the rule for BTCUSDT perpetual-style contract use with leverage awareness.

## Data-source expansion

V20 adds BTC contract data planning utilities:

- Binance USD-M Futures public data manifest for BTCUSDT daily files.
- K-line intervals: 1s, 5s, 15s, 1m, 5m, 15m.
- Aggregate-trade files for trade-flow features.
- REST task templates for Binance funding, open interest, mark-price features.
- REST task templates for Bybit kline, funding, and open-interest cross-venue validation.

Generated plan:

```text
runs/research_v20_btc_contract_data_plan/
rows: 6244 Binance public-data rows for 2024-01-01 through 2026-06-10
```

V20 does not claim these external files were downloaded inside the build sandbox. It writes reproducible manifests and download commands so the next worker can sync the BTC data locally and run forward validation.

## Frozen V19 input

```text
symbol focus: BTCUSDT / BTC perpetual contracts
user taker fee: 0.0400% per side = 4 bps per side
user maker fee: 0.0000% per side
selected execution route: taker entry + taker exit
round-trip fee: 8 bps
horizon: 90 sec
base latency: 0.5 sec
take profit: 40 bps
stop loss: disabled
```

V19 high-fee filters remain:

```text
signal * kline_15s_signal >= -0.7266055861290821
kline_1m_rv_3_bps <= 17.890597279145457
kline_1m_range_z_6 >= -1.3068193253455331
```

## New BTC-specific guard

The bundled BTC sample showed the V19 loss was a long trade during a positive 15s K-line background. V20 adds a long-side BTC guard:

```text
if direction is long: require kline_15s_signal <= 0.0
if direction is short: no extra side guard
```

This removes one weak long slot while preserving the slot schedule. It does not add replacement trades.

## V20 aggregate result

Run:

```text
runs/research_v20_btc_contract_leverage_lock
```

| Metric | V19 real fee | V20 BTC guard |
|---|---:|---:|
| Trades | 11 | 10 |
| Hit rate | 90.91% | 100.00% |
| Mean net PnL | +11.0505 bps | +12.8764 bps |
| Median net PnL | +4.6713 bps | +7.8579 bps |
| Total net PnL | +121.5554 bps | +128.7639 bps |
| Max drawdown | -7.2085 bps | +0.0000 bps |
| Profit factor | 17.8628 | inf |

## Fold metrics

| Fold | Trades | Hit rate | Mean net PnL | Total net PnL |
|---:|---:|---:|---:|---:|
| 1 | 2 | 100.00% | +26.1744 | +52.3488 |
| 2 | 2 | 100.00% | +17.0538 | +34.1077 |
| 3 | 2 | 100.00% | +11.3811 | +22.7622 |
| 4 | 2 | 100.00% | +3.4776 | +6.9553 |
| 5 | 2 | 100.00% | +6.2950 | +12.5899 |

## Robustness checks

| Check | Result |
|---|---:|
| Gate passed | true |
| Bootstrap mean p05 | +6.1083 bps/trade |
| Bootstrap total p05 | +61.0833 bps |
| 5 equal-trade blocks positive | 5 / 5 |
| Leave-one-trade-out min total | +87.4597 bps |
| Leave-one-fold-out min total | +76.4151 bps |
| Remove top 5 winners total | +12.2981 bps |
| 50% missed-trade p05 total | +15.6448 bps |
| 50% missed-trade positive rate | 99.89% |
| Extra +10 bps/trade total | +28.7639 bps |
| Extra +12 bps/trade total | +8.7639 bps |

## Side-guard family null

```text
shifted null runs: 1000
candidate count: 8
selected total: +128.7639 bps
selected mean: +12.8764 bps/trade
null max total: +21.5873 bps
null max mean: +2.1587 bps/trade
add-one p(total): 0.000999
add-one p(mean): 0.000999
```

## Fee and latency stress

Stress grid:

```text
taker fee per side: 4, 5, 6, 7.5, 10 bps
latency: 0, 0.5, 1, 2, 3, 5 sec
```

Promoted stress region:

```text
positive through taker fee <= 7.5 bps per side
positive through latency <= 5 sec
worst promoted-stress total: +49.2816 bps
worst promoted-stress mean: +4.9282 bps/trade
```

Extreme warning:

```text
taker fee = 10 bps per side
latency = 5 sec
total = -0.7184 bps
mean = -0.0718 bps/trade
```

## Leverage scenarios

The package writes approximate account-return scenarios in:

```text
runs/research_v20_btc_contract_leverage_lock/btc_leverage_scenarios.csv
```

| Leverage | Approx total account return, no compounding | Approx liquidation buffer before safety shock |
|---:|---:|---:|
| 1x | +1.2876% | 9942.0 bps |
| 2x | +2.5753% | 4942.0 bps |
| 3x | +3.8629% | 3275.3 bps |
| 5x | +6.4382% | 1942.0 bps |
| 10x | +12.8764% | 942.0 bps |
| 20x | +25.7528% | 442.0 bps |

Promoted leverage cap remains 3x because this is still a bundled-sample research result. Higher leverage is reported for simulation only, not promoted.

## Added files

```text
src/lob_microprice_lab/btc_contract_data.py
src/lob_microprice_lab/btc_leverage_lock.py
scripts/run_btc_contract_leverage_lock_v20.py
scripts/run_btc_contract_leverage_v20.py
tests/test_btc_contract_v20.py
tests/test_btc_leverage_lock_v20.py
docs/RESEARCH_V20_COMMANDS.md
reports/RESEARCH_V20_RESULTS.md
runs/research_v20_btc_contract_leverage_lock/
runs/research_v20_btc_contract_data_plan/
```

## Status

```text
BTC data-source search and manifests: completed
V19 real-fee rule reproduced: completed
BTC-specific side guard: completed
V20 bundled-sample research gate: passed
Promoted leverage cap: 3x research-only
Independent multi-day BTC contract validation: not yet completed
Live trading readiness: not proven
```

## Caveat

V20 improves the bundled BTC sample and gives a concrete BTC data-sync plan, but it is still not proof of future stable profit. The V20 side guard should now be frozen and tested on independent BTC contract days before any live use.
