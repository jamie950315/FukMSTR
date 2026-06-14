# Research V60 Commands

Purpose: rank the V59 parameter neighborhood using design folds only, then report holdout fold performance for the selected candidate and the fixed V55/V57 rule.

## Run

```bash
make btcusdc-sparse-tp-design-selector-v60
```

## Targeted Tests

```bash
make test-btcusdc-v60
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Primary Outputs

```text
runs/research_v60_btcusdc_sparse_tp_design_selector_audit/v60_design_selector_candidate_evaluations.csv
runs/research_v60_btcusdc_sparse_tp_design_selector_audit/v60_summary.json
reports/RESEARCH_V60_DESIGN_SELECTOR_AUDIT_RESULTS.md
```
