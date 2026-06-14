# Research V27 Commands

V27 adds a BTCUSDC independent public 1m kline calibration/validation audit.

## Run

```bash
make btcusdc-independent-validation-v27
```

Input files are the downloaded BTCUSDC Binance USD-M public 1m kline zip files under:

```text
data/binance_public/binance/um/daily/klines/BTCUSDC/1m/
```

The default split is:

- Calibration: 2026-05-22 through 2026-05-31
- Validation: 2026-06-01 through 2026-06-10

## Test

```bash
make test-btcusdc-v27
```

## Outputs

```text
runs/research_v27_btcusdc_independent_validation/summary_v27.json
runs/research_v27_btcusdc_independent_validation/REPORT_V27.md
runs/research_v27_btcusdc_independent_validation/btcusdc_v27_candidate_evaluations.csv
runs/research_v27_btcusdc_independent_validation/btcusdc_v27_calibration_trades.csv
runs/research_v27_btcusdc_independent_validation/btcusdc_v27_validation_trades.csv
runs/research_v27_btcusdc_independent_validation/btcusdc_v27_calibration_daily.csv
runs/research_v27_btcusdc_independent_validation/btcusdc_v27_validation_daily.csv
```

## Caveat

This is a public 1m kline validation audit. It is not an L2 order-book replay and it is not proof of future profitability.
