# Research V77 Commands

Run the bucket transfer stability audit:

```bash
make btcusdc-fixed-flow-bucket-transfer-stability-v77
```

Run the focused test target:

```bash
make test-btcusdc-v77
```

The audit compares design folds against holdout folds on the selected V75 kept ledger under the V72 execution contract. It checks signal hour, entry hour, UTC month, and delay transfer stability. It does not tune thresholds, exclude new buckets, or promote a new policy.
