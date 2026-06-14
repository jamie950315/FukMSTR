# Research V90 Commands

V90 forward-monitors the V69/V87/V89 BTCUSDC fixed-flow policies after the V89 cutoff.

## Downloaded Files Used

- `data/binance_public/um/daily/aggTrades/BTCUSDC/BTCUSDC-aggTrades-2026-06-11.zip`
- `data/binance_public/um/daily/aggTrades/BTCUSDC/BTCUSDC-aggTrades-2026-06-12.zip`
- `data/binance_public/um/daily/klines/BTCUSDC/1m/BTCUSDC-1m-2026-06-11.zip`
- `data/binance_public/um/daily/klines/BTCUSDC/1m/BTCUSDC-1m-2026-06-12.zip`

## Run

```bash
make btcusdc-forward-monitoring-v90
```

## Run Latest Two-Year Window

```bash
make btcusdc-v90-two-year-window
```

## Focused Test

```bash
make test-btcusdc-v90
```

## Full Test Suite

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
```

## Build

```bash
python -m build
```

## Outputs

- `runs/research_v90_btcusdc_forward_monitoring/v90_summary.json`
- `runs/research_v90_btcusdc_forward_monitoring/v90_policy_monitoring.csv`
- `runs/research_v90_btcusdc_forward_monitoring/v90_new_aggtrade_1m_flow_bars.csv`
- `reports/RESEARCH_V90_BTCUSDC_FORWARD_MONITORING_RESULTS.md`
- `runs/research_v90_btcusdc_two_year_window/v90_two_year_summary.json`
- `runs/research_v90_btcusdc_two_year_window/v90_two_year_policy_table.csv`
- `reports/RESEARCH_V90_BTCUSDC_TWO_YEAR_WINDOW_RESULTS.md`
