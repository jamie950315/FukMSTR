# Research V92 Commands: BTCUSDC Earliest-to-Latest Window

V92 applies the fixed V90 BTCUSDC policy family to the full available BTCUSDC aggTrade flow window. It does not retune thresholds or hour filters.

## Run Full Available Window

```bash
make btcusdc-v92-earliest-to-latest-window
```

The current run uses the existing V50 full BTCUSDC bars and V90 public-data refresh path. Binance public BTCUSDC aggTrades are available from `2024-01-04`; the `2026-06-13` daily file was not yet available at run time, so the latest complete data end is `2026-06-12T23:59:00Z`.

## Test

```bash
make test-btcusdc-v92
```

## Outputs

```text
runs/research_v92_btcusdc_earliest_to_latest_window/v92_full_window_summary.json
runs/research_v92_btcusdc_earliest_to_latest_window/v92_full_window_policy_table.csv
reports/RESEARCH_V92_BTCUSDC_EARLIEST_TO_LATEST_RESULTS.md
```
