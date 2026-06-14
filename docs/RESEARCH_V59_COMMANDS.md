# Research V59 Commands

Purpose: audit whether the fixed V55/V57 sparse BTCUSDC TP80 rule is isolated in a nearby parameter family.

## Run

```bash
make btcusdc-sparse-tp-neighborhood-v59
```

## Targeted Tests

```bash
make test-btcusdc-v59
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Primary Outputs

```text
runs/research_v59_btcusdc_sparse_tp_neighborhood_audit/v59_neighborhood_candidate_evaluations.csv
runs/research_v59_btcusdc_sparse_tp_neighborhood_audit/v59_summary.json
reports/RESEARCH_V59_NEIGHBORHOOD_AUDIT_RESULTS.md
```
