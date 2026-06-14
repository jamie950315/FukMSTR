# Research V96 Commands: BTCUSDC ML Probability Gate

V96 scans BTCUSDC 1m aggTrade flow bars with a logistic probability gate. It targets strategies with positive selector and holdout PnL, win rate above 55%, and at least one trade per calendar day on average.

Run the scan:

```bash
make btcusdc-ml-probability-gate-v96
```

Run the focused V96 tests:

```bash
make test-btcusdc-v96
```

Outputs:

```text
runs/research_v96_btcusdc_ml_probability_gate/v96_summary.json
runs/research_v96_btcusdc_ml_probability_gate/v96_ml_probability_candidates.csv
runs/research_v96_btcusdc_ml_probability_gate/v96_ml_probability_passed_candidates.csv
reports/RESEARCH_V96_BTCUSDC_ML_PROBABILITY_GATE_RESULTS.md
```

The model is trained before the selector window. Probability thresholds are evaluated on the selector and holdout windows. It is a research scan, not a live trading guarantee.
