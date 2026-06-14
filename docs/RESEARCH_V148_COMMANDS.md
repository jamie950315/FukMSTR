# Research V148 Commands

V148 tests Binance BTCUSDC premium index klines as a derivatives sentiment and basis overlay on top of the V144 account path.

The experiment uses only closed premium-index klines. A trade inside the current hour can only see the prior closed premium kline, avoiding current-hour close leakage.

## Run

```bash
make btcusdc-v148-premium-basis-sentiment-overlay
```

## Focused Test

```bash
make test-btcusdc-v148
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

Generated local outputs are written under:

```text
runs/research_v148_premium_basis_sentiment_overlay/
```

The committed report is:

```text
reports/RESEARCH_V148_BTCUSDC_PREMIUM_BASIS_SENTIMENT_OVERLAY.md
```

## Source

```text
https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Premium-Index-Kline-Data
```
