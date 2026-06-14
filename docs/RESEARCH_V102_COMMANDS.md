# Research V102 Commands

Run the MA-feature thick-edge regression scan:

```bash
make btcusdc-ma-feature-regression-v102
```

Run the focused V102 tests:

```bash
make test-btcusdc-v102
```

Outputs:

```text
runs/research_v102_btcusdc_ma_feature_regression/v102_ma_feature_candidates.csv
runs/research_v102_btcusdc_ma_feature_regression/v102_ma_feature_passed_candidates.csv
runs/research_v102_btcusdc_ma_feature_regression/v102_summary.json
reports/RESEARCH_V102_BTCUSDC_MA_FEATURE_REGRESSION_RESULTS.md
```

V102 adds MA7, MA25, and MA99 trend-structure features to the V101 thick-edge regression route. The moving averages are computed from prior close values to avoid lookahead.
