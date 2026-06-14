# Research V75 Commands

Run the design-selected combined policy audit:

```bash
make btcusdc-fixed-flow-design-selected-combined-policy-v75
```

Run the focused test target:

```bash
make test-btcusdc-v75
```

The audit selects a monthly cooldown policy using only design folds under the V72 execution contract, then evaluates the selected policy on the full and holdout ledgers. Cooldown 0 is included as the no-cooldown baseline.
