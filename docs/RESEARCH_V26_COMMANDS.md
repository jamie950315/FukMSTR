# Research V26 Commands: BTCUSDC Contract Lock

## Reproduce the included BTCUSDC transfer proxy run

```bash
make btcusdc-contract-lock-v26
```

Read the report:

```bash
cat reports/RESEARCH_V26_RESULTS.md
cat runs/research_v26_btcusdc_contract_lock/REPORT_V26.md
```

## Run tests

```bash
make test-btcusdc-v26
make test-split
```

## Download BTCUSDC public files locally

The included sandbox cannot download external files, but V26 writes the full BTCUSDC public-data download plan here:

```text
runs/research_v26_btcusdc_contract_lock/btcusdc_data_plan/download_commands.sh
```

On a machine with internet access:

```bash
bash runs/research_v26_btcusdc_contract_lock/btcusdc_data_plan/download_commands.sh
```

## True BTCUSDC replay mode

If you have a real BTCUSDC trade ledger with the same columns as `btc_adaptive_exit_trade_ledger.csv`, run:

```python
from lob_microprice_lab.btcusdc_contract_lock import run_btcusdc_contract_lock

run_btcusdc_contract_lock(
    v24_run_dir="runs/research_v24_btc_adaptive_exit_safety_lock",
    out_dir="runs/research_v26_btcusdc_true_replay",
    btcusdc_ledger="/path/to/btcusdc_real_ledger.csv",
    clean=True,
)
```

The output field `true_btcusdc_data_run_completed` must be `true` before treating the result as an actual BTCUSDC validation.

## Important interpretation

The included V26 result is a transfer proxy: it keeps the BTC rule frozen, applies the user fee, subtracts a BTCUSDC quote-market surcharge, and checks stress survivability. It is useful for system design, but not independent BTCUSDC market proof.
