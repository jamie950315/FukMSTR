# Research V56 Results: BTCUSDC Sparse TP80 Entry-Delay Stress

V56 stress-tests the V55 sparse TP80 result by delaying entry after the signal bar. It keeps the same rule, same TP80 exit, same data, and same V26 BTCUSDC gate.

## Rule Under Stress

```text
lookback: 1440 minutes
direction: reversal
filter: abs_return_bps
quantile: 0.995, recalibrated from each fold's calibration window
take profit: 80 bps
roundtrip taker fee: 8.0 bps
BTCUSDC surcharge: 0.5 bps through the existing V26 gate path
entry delays tested: 1, 2, 5, 10, 15, 30, 60 minutes after signal bar
```

Repro command:

```bash
make btcusdc-sparse-tp-entry-delay-v56
```

Output:

```text
runs/research_v56_btcusdc_sparse_tp_entry_delay_stress
```

## Gate Summary

| Entry delay | Gate passed | Trades | Win rate | Total bps | Mean bps | Worst trade | Failed checks |
|---:|---|---:|---:|---:|---:|---:|---|
| 1m | true | 11 | 100.00% | +786.5000 | +71.5000 | +71.5000 | none |
| 2m | true | 11 | 100.00% | +786.5000 | +71.5000 | +71.5000 | none |
| 5m | true | 11 | 100.00% | +786.5000 | +71.5000 | +71.5000 | none |
| 10m | true | 11 | 100.00% | +786.5000 | +71.5000 | +71.5000 | none |
| 15m | true | 11 | 100.00% | +786.5000 | +71.5000 | +71.5000 | none |
| 30m | true | 11 | 100.00% | +786.5000 | +71.5000 | +71.5000 | none |
| 60m | false | 11 | 90.91% | +495.1450 | +45.0132 | -219.8550 | missed_trade_account_return; synthetic_loss_drawdown |

## Conclusion

The V55 next-open result is not dependent on exact next-minute execution. The same sparse TP80 rule still passes the full V26 BTCUSDC gate with entry delayed up to 30 minutes after the signal bar. It fails at a 60-minute entry delay due to the missed-trade stress and synthetic-loss drawdown checks.

The main remaining caveat remains sample size: all passing runs still use only 11 trades.

