# Research V97 Commands: BTCUSDC HGB Regime Gate

V97 scans BTCUSDC 1m aggTrade flow bars with a HistGradientBoosting classifier plus selector-only regime gates. It targets strategies with positive selector and holdout PnL, win rate above 55%, and at least one trade per calendar day on average.

Run the scan:

```bash
make btcusdc-hgb-regime-gate-v97
```

Run the focused V97 tests:

```bash
make test-btcusdc-v97
```

Outputs:

```text
runs/research_v97_btcusdc_hgb_regime_gate/v97_summary.json
runs/research_v97_btcusdc_hgb_regime_gate/v97_hgb_regime_candidates.csv
runs/research_v97_btcusdc_hgb_regime_gate/v97_hgb_regime_passed_candidates.csv
reports/RESEARCH_V97_BTCUSDC_HGB_REGIME_GATE_RESULTS.md
```

The model is trained before the selector window. Probability thresholds and regime gates are evaluated on selector and holdout windows. It is a research scan, not a live trading guarantee.
