# Research V84 Commands

Run the BTCUSDC exit/lane bucket audit:

```bash
make btcusdc-exit-lane-bucket-audit-v84
```

Run the focused test target:

```bash
make test-btcusdc-v84
```

This audit checks whether any V26 BTCUSDC full public replay subset is stable by pretrade fields such as lane, side, take-profit size, or hold time. It reports exit reason separately as an outcome-only bucket.
