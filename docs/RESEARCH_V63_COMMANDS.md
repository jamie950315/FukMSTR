# Research V63 Commands

V63 explains the single V62 delay=5 holdout entry-delay failure without changing thresholds or the V60 design-selected sparse TP rule.

## Run audit

```bash
make btcusdc-sparse-tp-delay5-anomaly-v63
```

## Test

```bash
make test-btcusdc-v63
```

## Full verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Expected outputs

```text
runs/research_v63_btcusdc_sparse_tp_delay5_anomaly_audit/v63_all_delay_outcomes_annotated.csv
runs/research_v63_btcusdc_sparse_tp_delay5_anomaly_audit/v63_delay5_anomaly_delay_comparison.csv
runs/research_v63_btcusdc_sparse_tp_delay5_anomaly_audit/v63_delay5_anomaly_price_path.csv
runs/research_v63_btcusdc_sparse_tp_delay5_anomaly_audit/v63_summary.json
reports/RESEARCH_V63_DELAY5_ANOMALY_AUDIT_RESULTS.md
```
