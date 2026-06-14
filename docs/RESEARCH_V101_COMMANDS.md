# Research V101 Commands

Run the thick-edge regression scan for BTCUSDC high-frequency candidates:

```bash
make btcusdc-thick-edge-regression-v101
```

Run the focused V101 tests:

```bash
make test-btcusdc-v101
```

Outputs:

```text
runs/research_v101_btcusdc_thick_edge_regression/v101_thick_edge_candidates.csv
runs/research_v101_btcusdc_thick_edge_regression/v101_thick_edge_passed_candidates.csv
runs/research_v101_btcusdc_thick_edge_regression/v101_summary.json
reports/RESEARCH_V101_BTCUSDC_THICK_EDGE_REGRESSION_RESULTS.md
```

V101 uses return-magnitude regression instead of direction-probability classification. It keeps the existing 8.5 bps round-trip cost and evaluates selector and holdout windows without retuning on holdout.
