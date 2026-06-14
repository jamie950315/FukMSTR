# Research V64 Commands

V64 scans every entry delay from 0 to 120 minutes for the V60 design-selected BTCUSDC sparse TP rule on holdout folds only.

The rule and performance thresholds are unchanged. The script evaluates the V26 contract checks in-memory and treats the existing BTCUSDC data manifest as already written, avoiding 121 duplicate manifest directories.

## Run audit

```bash
make btcusdc-sparse-tp-dense-delay-scan-v64
```

## Test

```bash
make test-btcusdc-v64
```

## Full verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Expected outputs

```text
runs/research_v64_btcusdc_sparse_tp_dense_delay_scan/v64_delay0_holdout_base_signal_entries.csv
runs/research_v64_btcusdc_sparse_tp_dense_delay_scan/v64_dense_delay_contract_gate_summary.csv
runs/research_v64_btcusdc_sparse_tp_dense_delay_scan/v64_dense_delay_pass_fail_ranges.csv
runs/research_v64_btcusdc_sparse_tp_dense_delay_scan/v64_dense_delay_combined_tp80_ledger.csv
runs/research_v64_btcusdc_sparse_tp_dense_delay_scan/v64_dense_delay_worst10.csv
runs/research_v64_btcusdc_sparse_tp_dense_delay_scan/v64_summary.json
reports/RESEARCH_V64_DENSE_DELAY_SCAN_RESULTS.md
```
