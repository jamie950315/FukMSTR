# V23 BTC Adaptive Safety Lock Results

V23 keeps the V22 BTC trade rule frozen and adds an adaptive account-level leverage safety layer. It uses the user's real fee assumption:

```text
taker fee: 0.0400% per side = 4 bps per side
maker fee: 0.0000% per side
research route: taker entry + taker exit = 8 bps round trip
```

## Main run

```text
runs/research_v23_btc_adaptive_safety_lock
```

## Frozen trade rule

```text
V22 entry rule unchanged
V22 rescue lane unchanged
horizon: 90 seconds
take profit: 52 bps
stop loss: disabled
reserved horizon slot: enabled
```

## New V23 leverage safety policy

```text
normal leverage cap: 5.0x
risk-off leverage: 4.0x
risk-off trigger: realized trade <= -20 bps notional
risk-off duration: next 3 trades
```

## Result summary

| Metric | V23 |
|---|---:|
| Gate passed | true |
| Selected trades | 11 |
| Selected-trade win rate | 100.00% |
| Notional total net PnL | +183.7545 bps |
| Notional mean net PnL | +16.7050 bps/trade |
| Normal leverage | 5.0x |
| No-loss account return, no compounding | +9.1877% |
| Extreme 10 bps/side + 5 sec account return | +1.1186% |
| 50% missed-trade p05 account return | +1.1712% |
| Extra +16 bps/trade account return | +0.3877% |
| Entry/exit family add-one p(total) | 0.000999 |
| Entry/exit family add-one p(mean) | 0.000999 |

## Synthetic failure stress

V23 injects synthetic losing trades into the otherwise frozen V22 ledger.

| Stress item | Result |
|---|---:|
| Synthetic loss size | -40.0 bps notional |
| Synthetic loss count gate | 3 |
| Minimum account return after injected losses | +1.3648% |
| p05 account return after injected losses | +1.7463% |
| Worst drawdown after injected losses | -4.9218% |

The 4-loss row is intentionally not promoted: it turns negative in the generated stress table. The V23 target is therefore **three -40 bps synthetic failures while still staying above +1% account return and above -5% drawdown**.

## Status

```text
V22 BTC trade rule: frozen
V23 account-level safety: added
5x research cap: promoted under this bundled sample
selected-trade win rate: 100.00%
independent multi-day BTC validation: still required
live stable profit: not yet proven
```
