# Research V82 Commands

Run the BTCUSDC signal inversion audit:

```bash
make btcusdc-signal-inversion-audit-v82
```

Run the focused test target:

```bash
make test-btcusdc-v82
```

This audit checks whether the failed BTCUSDC public replay can be rescued by flipping trade direction. It charges the same execution cost after inversion and does not tune thresholds.
