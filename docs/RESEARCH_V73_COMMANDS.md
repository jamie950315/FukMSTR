# Research V73 Commands

Run the causal monthly cooldown audit for the V69/V72 fixed-flow BTCUSDC candidate:

```bash
make btcusdc-fixed-flow-monthly-cooldown-v73
```

Run the focused test target:

```bash
make test-btcusdc-v73
```

The audit selects a monthly cooldown policy using design folds only, then evaluates the selected policy on the full ledger and holdout folds. A cooldown month can only be triggered by already-realized monthly losses.
