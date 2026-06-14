# Research V110 Commands

V110 adds causal BTCUSDC order-flow, sweep/divergence, trade-intensity, and volatility-regime features, then compares selector-locked exact-daily ensembles against V109.

```bash
make test-btcusdc-v110
make btcusdc-flow-sweep-regime-ensemble-v110
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

Expected outputs:

- `runs/research_v110_btcusdc_flow_sweep_regime_ensemble/v110_flow_sweep_regime_ensemble_candidates.csv`
- `runs/research_v110_btcusdc_flow_sweep_regime_ensemble/v110_flow_sweep_regime_ensemble_passed_candidates.csv`
- `runs/research_v110_btcusdc_flow_sweep_regime_ensemble/v110_selector_locked_selected_candidate.csv`
- `runs/research_v110_btcusdc_flow_sweep_regime_ensemble/v110_summary.json`
- `reports/RESEARCH_V110_BTCUSDC_FLOW_SWEEP_REGIME_ENSEMBLE_RESULTS.md`
