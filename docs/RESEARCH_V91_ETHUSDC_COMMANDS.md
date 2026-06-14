# Research V91 Commands: ETHUSDC V90 Transfer Test

V91 applies the fixed BTCUSDC V90 policy family directly to ETHUSDC public aggTrade flow data. It does not retune thresholds or hour filters for ETHUSDC.

## Run ETHUSDC Transfer Test

```bash
make ethusdc-v90-transfer-test-v91
```

The runner downloads missing Binance USD-M ETHUSDC public aggTrade files into:

```text
data/binance_public/um/monthly/aggTrades/ETHUSDC/
data/binance_public/um/daily/aggTrades/ETHUSDC/
```

It uses monthly files for `2024-06` through `2026-05` and daily files for `2026-06-01` through `2026-06-12`.

## Test

```bash
make test-ethusdc-v91
```

## Outputs

```text
runs/research_v91_ethusdc_v90_transfer_test/v91_ethusdc_summary.json
runs/research_v91_ethusdc_v90_transfer_test/v91_ethusdc_policy_table.csv
runs/research_v91_ethusdc_v90_transfer_test/v91_ethusdc_aggtrade_1m_flow_bars.csv
reports/RESEARCH_V91_ETHUSDC_V90_TRANSFER_TEST_RESULTS.md
```
