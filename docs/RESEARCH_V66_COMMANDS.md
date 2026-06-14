# Research V66 Commands

V66 ranks the V59 parameter neighborhood by dense entry-delay robustness on design folds only, then evaluates the design-selected candidate on holdout folds.

It does not change the TP80 exit, no-stop policy, V26 contract gate settings, or the V59 parameter grid.

## Run audit

```bash
make btcusdc-sparse-tp-design-robust-selector-v66
```

## Test

```bash
make test-btcusdc-v66
```

## Full verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Expected outputs

```text
runs/research_v66_btcusdc_sparse_tp_design_robust_selector/v66_design_delay_robust_candidate_rankings.csv
runs/research_v66_btcusdc_sparse_tp_design_robust_selector/v66_selected_holdout_dense_delay_contract_gate_summary.csv
runs/research_v66_btcusdc_sparse_tp_design_robust_selector/v66_selected_holdout_pass_fail_ranges.csv
runs/research_v66_btcusdc_sparse_tp_design_robust_selector/v66_selected_holdout_worst10.csv
runs/research_v66_btcusdc_sparse_tp_design_robust_selector/v66_v60_reference_holdout_dense_delay_contract_gate_summary.csv
runs/research_v66_btcusdc_sparse_tp_design_robust_selector/v66_summary.json
reports/RESEARCH_V66_DESIGN_ROBUST_SELECTOR_RESULTS.md
```
