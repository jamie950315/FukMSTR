# Research V78 Commands

Run the prequential bucket guard audit:

```bash
make btcusdc-fixed-flow-prequential-bucket-guard-v78
```

Run the focused test target:

```bash
make test-btcusdc-v78
```

The audit tests live-feasible bucket guards that learn only from prior kept trades within each delay scenario. It selects a guard using design folds only, then validates the selected guard on full and holdout folds. It does not change the original signal thresholds.
