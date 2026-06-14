# Research V81 Commands

Run the BTCUSDC fixed-family viability audit:

```bash
make btcusdc-fixed-family-viability-v81
```

Run the focused test target:

```bash
make test-btcusdc-v81
```

This audit groups the existing 2026 YTD rolling aggTrade-flow candidate evaluations by fixed family and checks whether any family is stable enough to justify more work. It does not tune thresholds or promote a route.
