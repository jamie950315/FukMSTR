# Research V57 Commands

Purpose: rerun the fixed V55 sparse BTCUSDC TP80 next-open rule on Binance public 1m kline bars and pass the resulting true BTCUSDC ledger through the unchanged V26 contract gate.

## Run

```bash
make btcusdc-sparse-tp-kline-confirm-v57
```

## Targeted Tests

```bash
make test-btcusdc-v57
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Primary Outputs

```text
runs/research_v57_btcusdc_sparse_tp_kline_confirm/v57_kline_next_open_entries.csv
runs/research_v57_btcusdc_sparse_tp_kline_confirm/v57_kline_next_open_tp80_ledger.csv
runs/research_v57_btcusdc_sparse_tp_kline_confirm/v57_kline_next_open_tp80_source_ledger_for_contract_gate.csv
runs/research_v57_btcusdc_sparse_tp_kline_confirm/v57_kline_vs_v55_entry_comparison.csv
runs/research_v57_btcusdc_sparse_tp_kline_confirm/v57_summary.json
runs/research_v57_btcusdc_sparse_tp_kline_confirm_contract_gate/summary.json
reports/RESEARCH_V57_KLINE_CONFIRM_RESULTS.md
```
