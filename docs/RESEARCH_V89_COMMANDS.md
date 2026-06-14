# Research V89 Commands

V89 scans pre-trade BTCUSDC stability-repair candidates on top of the V88 V87 two-year ledger.

## Run

```bash
make btcusdc-stability-improvement-scan-v89
```

## Focused Test

```bash
make test-btcusdc-v89
```

## Full Test Suite

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
```

## Build

```bash
python -m build
```

## Outputs

- `runs/research_v89_btcusdc_stability_improvement_scan/v89_summary.json`
- `runs/research_v89_btcusdc_stability_improvement_scan/v89_stability_repair_candidates.csv`
- `runs/research_v89_btcusdc_stability_improvement_scan/v89_selected_months.csv`
- `runs/research_v89_btcusdc_stability_improvement_scan/v89_conservative_same_family_months.csv`
- `reports/RESEARCH_V89_BTCUSDC_STABILITY_IMPROVEMENT_SCAN_RESULTS.md`
