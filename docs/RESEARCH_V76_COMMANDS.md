# Research V76 Commands

Run the holdout failure attribution audit:

```bash
make btcusdc-fixed-flow-holdout-failure-attribution-v76
```

Run the focused test target:

```bash
make test-btcusdc-v76
```

The audit explains the V75 holdout failure using the selected V75 kept ledger under the V72 execution contract. It only attributes loss by fold, month, UTC hour, and delay; it does not tune thresholds or promote a stronger policy.
