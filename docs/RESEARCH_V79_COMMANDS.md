# Research V79 Commands

Run the fixed-flow route closure audit:

```bash
make btcusdc-fixed-flow-route-closure-v79
```

Run the focused test target:

```bash
make test-btcusdc-v79
```

The audit combines existing V26, V68, V69, V70, V72, V75, V77, and V78 evidence into a route-level non-promotion certificate. It does not recalculate trades or change signal thresholds.
