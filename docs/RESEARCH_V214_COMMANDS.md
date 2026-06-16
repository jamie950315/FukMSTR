# Research V214 Commands

V214 adds a Binance public-data availability gate for BTCUSDC daily files. It checks whether the latest completed UTC day is published by Binance public data and whether the matching local aggTrade and 1m kline files are present.

V214 does not place live orders, tune thresholds, change entries, change exits, or change leverage rules.

## Run Focused Tests

```bash
make test-btcusdc-v214
```

## Run Public Data Availability Gate

```bash
make btcusdc-v214-public-data-availability-gate
```

## Required Inputs

The gate checks the latest completed UTC date. For example, when current UTC time is still `2026-06-16`, the latest completed UTC day is `2026-06-15`.

Expected local files:

```text
data/binance_public/um/daily/aggTrades/BTCUSDC/BTCUSDC-aggTrades-YYYY-MM-DD.zip
data/binance_public/um/daily/klines/BTCUSDC/1m/BTCUSDC-1m-YYYY-MM-DD.zip
```

## Outputs

```text
runs/research_v214_public_data_availability_gate/v214_public_data_availability_gate_summary.json
reports/RESEARCH_V214_BTCUSDC_PUBLIC_DATA_AVAILABILITY_GATE.md
```

The `runs/` output and local public data files are generated evidence and should not be committed.

## Real-Money Status

V214 alone never promotes real-money use. It only prevents stale or incomplete public data from being treated as current forward-monitoring evidence.
