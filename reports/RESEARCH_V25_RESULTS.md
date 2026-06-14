# Research V25 BTC Portfolio Risk Lock Results

V25 continues from V24 and keeps the BTC trading rule frozen.  It does not change entries, directions, fees, K-line guards, or exit targets.  The only V25 change is the account-level leverage governor.

## Frozen trading rule

```text
source: V24 BTC adaptive exit + safety lock
prediction window: 90 seconds
real fee: taker 0.0400% per side, maker 0.0000%
research route: taker entry + taker exit = 8 bps round trip
entries: unchanged from V24
adaptive exits: unchanged from V24
selected bundled-sample trades: unchanged from V24
```

## V25 promoted portfolio policy

```text
normal mode: 8.0x
emergency mode: 6.75x
trigger: any realized trade <= -20 bps notional
emergency duration: next 10 trades
shock buffer requirement: 1000 bps before estimated liquidation zone
```

This is a research-only leverage cap.  The live version must still check exchange leverage tiers, mark-price liquidation, margin mode, wallet balance, open notional, and maintenance margin before placing any order.

## Main V25 result

Main run:

```text
runs/research_v25_btc_portfolio_risk_lock
```

| Metric | V25 |
|---|---:|
| Gate passed | true |
| Trades | 11 |
| Selected-trade win rate | 100.00% |
| Notional total net PnL | +190.0977 bps |
| Notional mean net PnL | +17.2816 bps/trade |
| Normal leverage | 8.0x |
| Emergency leverage | 6.75x |
| No-loss account return, no compounding | +15.2078% |
| Entry/exit family p(total) | 0.000999 |
| Entry/exit family p(mean) | 0.000999 |
| Estimated liquidation buffer before safety shock | 1192.0 bps |
| Required shock buffer | 1000.0 bps |

## Improvement versus V24

| Metric | V24 | V25 |
|---|---:|---:|
| Trades | 11 | 11 |
| Selected-trade win rate | 100.00% | 100.00% |
| Notional total net PnL | +190.0977 bps | +190.0977 bps |
| Normal leverage | 5.0x | 8.0x |
| No-loss account return | +9.5049% | +15.2078% |
| Promoted synthetic loss count | 3 | 4 |
| Four-loss minimum account return | -0.3961% | +1.5316% |
| Four-loss worst drawdown | -6.0142% | -9.9739% |

V25 improves the account-level research target by increasing the promoted leverage cap while also changing the synthetic-loss gate from three artificial bad trades to four artificial bad trades.

## Stress checks at 8x

| Check | V25 |
|---|---:|
| Extreme 10 bps/side + 5 sec account return | +3.5724% |
| 50% missed-trade p05 account return | +2.0630% |
| Extra +16 bps/trade account return | +1.1278% |
| Four synthetic -40 bps losses, minimum account return | +1.5316% |
| Four synthetic -40 bps losses, p05 account return | +1.5316% |
| Four synthetic -40 bps losses, worst drawdown | -9.9739% |

Warning row:

```text
Five synthetic -40 bps failures are not promoted.
minimum account return: -1.1684%
worst drawdown: -12.5198%
```

So the V25 safety claim is limited to four synthetic -40 bps failures, not five.

## Files added or updated

```text
src/lob_microprice_lab/btc_portfolio_risk_lock.py
scripts/run_btc_portfolio_risk_lock_v25.py
tests/test_btc_portfolio_risk_lock_v25.py
docs/RESEARCH_V25_COMMANDS.md
reports/RESEARCH_V25_RESULTS.md
runs/research_v25_btc_portfolio_risk_lock/
runs/research_v25_summary.csv
```

## Current status

```text
V25 bundled-sample BTC target: reached
real-fee target: reached
selected-trade win-rate target: reached at 100.00%
8x research cap: reached
four synthetic-loss stress at 8x: passed
extreme fee/latency stress at 8x: passed
missed-trade stress at 8x: passed
extra-cost reserve at 8x: passed
independent multi-day BTCUSDT validation: still required
live stable profit: not yet proven
```

V25 should now be frozen before independent BTCUSDT futures validation.  Do not tune the 8.0x / 6.75x / four-loss policy on the bundled sample again.
