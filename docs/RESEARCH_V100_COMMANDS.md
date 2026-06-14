# Research V100 Commands

Run the maker fill risk stress test for the V99 BTCUSDC low-cost high-frequency candidate:

```bash
make btcusdc-maker-fill-risk-v100
```

Run the focused V100 tests:

```bash
make test-btcusdc-v100
```

Outputs:

```text
runs/research_v100_btcusdc_maker_fill_risk/v100_maker_fill_stress.csv
runs/research_v100_btcusdc_maker_fill_risk/v100_summary.json
reports/RESEARCH_V100_BTCUSDC_MAKER_FILL_RISK_RESULTS.md
```

V100 keeps the V99 candidate and thresholds unchanged. It tests whether the candidate survives missed fills and adverse-selection fills that are plausible for maker-style execution.
