# Research V145 Commands

V145 adds a recent derivatives-sentiment monitor on top of the V144 BTCUSDC account path.

It downloads the latest Binance USD-M BTCUSDC:

- Open interest statistics
- Global long/short account ratio
- Top trader long/short account ratio
- Top trader long/short position ratio

Binance documents these endpoints as latest-30-day/latest-1-month datasets, so V145 is intentionally a forward-monitoring artifact rather than a two-year strategy promotion.

## Run

```bash
make btcusdc-v145-derivatives-sentiment-monitor
```

## Focused Test

```bash
make test-btcusdc-v145
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

Generated local outputs are written under:

```text
runs/research_v145_derivatives_sentiment_monitor/
```

The committed report is:

```text
reports/RESEARCH_V145_BTCUSDC_DERIVATIVES_SENTIMENT_MONITOR.md
```
