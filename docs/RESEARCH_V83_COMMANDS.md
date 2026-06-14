# Research V83 Commands

Run the BTCUSDC cost edge audit:

```bash
make btcusdc-cost-edge-audit-v83
```

Run the focused test target:

```bash
make test-btcusdc-v83
```

This audit separates gross signal edge from execution cost on the V26 BTCUSDC full public replay ledger. It checks original and inverted directions across a fixed cost grid and does not tune thresholds.
