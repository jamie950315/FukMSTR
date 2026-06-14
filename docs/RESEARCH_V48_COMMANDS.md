# Research V48 Commands

V48 tests a direct BTCUSDC public 1m bar Ridge model after the full available V26 true BTCUSDC replay failed.

## Run

```bash
make btcusdc-full-1m-direct-ml-v48
```

Main output:

```text
runs/research_v48_btcusdc_full_1m_direct_ml_probe
```

Input cache:

```text
runs/research_v48_btcusdc_full_1m_direct_ml_input/btcusdc_full_1m_bars.csv
```

## Test

```bash
make test-btcusdc-v48
```

## Notes

The run uses only public BTCUSDC 1m bars already downloaded from Binance public files. It does not reuse the transferred BTC rule and does not change the V26 BTCUSDC gate. The result is a probe, not a promoted strategy.
