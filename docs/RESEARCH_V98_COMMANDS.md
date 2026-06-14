# Research V98 Commands: BTCUSDC Cost Sensitivity

V98 replays the V97 HGB regime candidate grid under alternative fee assumptions without changing probability or regime thresholds. It checks whether high-frequency failure is mainly caused by round-trip cost.

Run the scan:

```bash
make btcusdc-cost-sensitivity-v98
```

Run the focused V98 tests:

```bash
make test-btcusdc-v98
```

Outputs:

```text
runs/research_v98_btcusdc_cost_sensitivity/v98_summary.json
runs/research_v98_btcusdc_cost_sensitivity/v98_cost_sensitivity_candidates.csv
runs/research_v98_btcusdc_cost_sensitivity/v98_cost_sensitivity_passed_candidates.csv
runs/research_v98_btcusdc_cost_sensitivity/v98_cost_sensitivity_fee_summary.csv
reports/RESEARCH_V98_BTCUSDC_COST_SENSITIVITY_RESULTS.md
```

The tested fee scenarios are 8.5 bps, 4.0 bps, and 0.0 bps per completed trade. This is a research scan, not a live trading guarantee.
