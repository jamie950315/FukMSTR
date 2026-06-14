# Research V28 Commands

V28 adds rolling-forward BTCUSDC validation on Binance USD-M public 1m klines.

## Run

```bash
make btcusdc-rolling-forward-v28
```

Default range:

- Data: 2026-03-13 through 2026-06-10
- Calibration window: 20 days
- Validation window: 10 days
- Step: 10 days
- Risk gate: trade only when the selected calibration candidate has at least 25% account return at 8x

## Test

```bash
make test-btcusdc-v28
```

## Outputs

```text
runs/research_v28_btcusdc_rolling_forward/summary_v28.json
runs/research_v28_btcusdc_rolling_forward/REPORT_V28.md
runs/research_v28_btcusdc_rolling_forward/btcusdc_v28_fold_metrics.csv
runs/research_v28_btcusdc_rolling_forward/btcusdc_v28_candidate_evaluations.csv
runs/research_v28_btcusdc_rolling_forward/btcusdc_v28_validation_trades.csv
runs/research_v28_btcusdc_rolling_forward_input/downloaded_btcusdc_1m_klines.csv
```

## Caveat

This is still public 1m kline validation. It is stronger than a single V27 split, but not a production L2 order-book replay.
