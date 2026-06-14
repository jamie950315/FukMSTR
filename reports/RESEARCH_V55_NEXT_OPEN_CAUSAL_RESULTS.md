# Research V55 Results: BTCUSDC Sparse TP80 Next-Open Causal Check

V55 checks whether the V54 sparse TP80 BTCUSDC gate pass survives a stricter causal entry assumption.

V54 formed the signal on a 1m bar and entered at that bar's open. V55 keeps the same rule and gate, but delays entry to the next 1m open:

```text
signal at bar t
entry at bar t+1 open
take profit: 80 bps
horizon reserve: 1440 minutes from delayed entry
```

## Rule

```text
lookback: 1440 minutes
direction: reversal
filter: abs_return_bps
quantile: 0.995, recalibrated from each fold's calibration window
entry: next 1m open after the signal bar
take profit: 80 bps
roundtrip taker fee: 8.0 bps
BTCUSDC surcharge: 0.5 bps through the existing V26 gate path
```

## Output

```text
runs/research_v55_btcusdc_sparse_tp_next_open_causal
runs/research_v55_btcusdc_sparse_tp_next_open_contract_gate
```

Repro command:

```bash
make btcusdc-sparse-tp-next-open-v55
```

## Gate Result

| Metric | Value |
|---|---:|
| Gate passed | true |
| Trades | 11 |
| Win rate | 100.00% |
| Notional total net PnL | +786.5000 bps |
| Notional mean net PnL | +71.5000 bps/trade |
| Worst trade | +71.5000 bps |
| Account return at 8x/no compounding | +62.9200% |
| Account max drawdown | 0.0000% |
| Bootstrap positive total rate | 100.00% |
| 50% missed-trade p05 account return | +17.1600% |
| Extra +16 bps/trade account return | +48.8400% |
| Four synthetic -40 bps failures min account return | +40.1225% |
| Four synthetic -40 bps failures worst drawdown | -3.2000% |

All V26 gate checks passed.

## Trades

All 11 delayed entries hit TP80:

| Fold | Signal time UTC | Entry time UTC | Side | Exit reason | Net after all BTCUSDC costs |
|---:|---|---|---:|---|---:|
| 1 | 2025-04-07 06:35 | 2025-04-07 06:36 | long | take_profit | +71.5 bps |
| 1 | 2025-04-10 01:15 | 2025-04-10 01:16 | short | take_profit | +71.5 bps |
| 4 | 2025-10-10 21:17 | 2025-10-10 21:18 | long | take_profit | +71.5 bps |
| 4 | 2025-11-21 07:34 | 2025-11-21 07:35 | long | take_profit | +71.5 bps |
| 5 | 2025-12-02 19:31 | 2025-12-02 19:32 | short | take_profit | +71.5 bps |
| 6 | 2026-01-30 01:43 | 2026-01-30 01:44 | long | take_profit | +71.5 bps |
| 6 | 2026-01-31 18:44 | 2026-01-31 18:45 | long | take_profit | +71.5 bps |
| 6 | 2026-02-05 12:18 | 2026-02-05 12:19 | long | take_profit | +71.5 bps |
| 6 | 2026-02-06 20:16 | 2026-02-06 20:17 | short | take_profit | +71.5 bps |
| 6 | 2026-02-25 21:36 | 2026-02-25 21:37 | short | take_profit | +71.5 bps |
| 6 | 2026-03-04 15:20 | 2026-03-04 15:21 | short | take_profit | +71.5 bps |

## Conclusion

V55 preserves the V54 gate pass under a stricter next-open causal entry assumption. This removes the main same-bar open-entry concern. The remaining caveat is unchanged: the promoted ledger is sparse at 11 trades, so future unseen BTCUSDC data is still needed before treating this as production-robust.

