# FukMSTR

BTCUSDC short-term trading research, replay, and paper-trading tools.

This repository is a research workspace for testing short-horizon BTCUSDC signals, leverage rules, and historical replay behavior. It does not place live orders, does not connect to private exchange accounts, and should not be treated as a live trading guarantee.

## Current status

The official BTCUSDC online/paper iteration is V193:

- V193 is the promoted online/paper iteration for BTCUSDC monitoring and historical replay.
- V193 uses the V192 selected account path plus a top5 long-base premium-6h size throttle.
- The historical replay page is generated from the V193 account-return and PnL columns.
- V142 remains the legacy paper-trading CLI entrypoint name and historical compatibility layer.
- Side backfill still uses the V119 signal reference when older account-path ledgers omit `signal`.

The generated V193 replay data currently confirms that historical replay has no missing side labels:

```text
trades: 645
long: 513
short: 132
side = n/a: 0
```

The replay window is extended through the latest locally verified forward public data:

```text
period end: 2026-06-15T23:59:59.999999+00:00
last V193 trade: 2026-06-09T16:40:00+00:00
forward monitor through: 2026-06-15T23:59:00+00:00
new forward signals after freeze: 0
```

## Important warning

This is a research candidate, not a live trading system.

Before any real-money use, this still needs forward monitoring, exchange-specific execution testing, private risk controls, slippage checks, outage handling, and manual review. Historical positive results do not prove future profitability.

## Repository contents

```text
src/lob_microprice_lab/      Python package and CLI
tests/                       Regression tests
scripts/                     Research runners
configs/                     Example configs
docs/                        Command notes and schemas
reports/                     Research summaries
tradingview/                 TradingView Pine companion scripts
Makefile                     Reproducible research/test targets
```

Large local artifacts are intentionally ignored and are not part of the public repository:

```text
data/
runs/
build/
dist/
```

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .[dev]
```

Run the full test suite:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
```

Build the package:

```bash
python -m build
```

## V193 replay

Generate the historical replay page:

```bash
make trade-replay-v193-page
```

Output:

```text
runs/v142_trading_replay/index.html
runs/v142_trading_replay/replay_data.json
```

The replay page includes:

- balance chart
- playback controls
- visible trade log
- side and side source columns
- month and total performance fields

## TradingView companion

The TradingView companion Pine strategy is available at:

```text
tradingview/btcusdc_v193_companion_strategy.pine
```

Usage notes and limitations are documented in:

```text
docs/TRADINGVIEW_V193_COMPANION.md
```

This Pine script is an OHLCV-based companion for charting, backtesting, and alerts. It cannot exactly reproduce the backend V193 research path because TradingView cannot access the research account-path columns used by V193.

## Paper trading demo

Run the synthetic local demo:

```bash
make paper-trade-v142-demo
```

Output:

```text
runs/paper_v142_demo/dashboard.html
runs/paper_v142_demo/paper_events.jsonl
runs/paper_v142_demo/balance.csv
runs/paper_v142_demo/trades.csv
runs/paper_v142_demo/positions.csv
runs/paper_v142_demo/order_events.csv
runs/paper_v142_demo/decisions.csv
runs/paper_v142_demo/summary.json
```

The paper-trading tool is local simulation only. It records events and hypothetical trades but does not submit orders. The command name remains `paper-trade-v142` for compatibility; V193 is the official promoted online/paper iteration recorded in the strategy manifest.

## Realtime public data paper trading

Capture a short public Binance local order-book sample:

```bash
make collect-binance-ws-smoke
```

Run paper trading from that captured book CSV:

```bash
make paper-trade-v142-book-csv-smoke BOOK_CSV=data/binance/BTCUSDT_ws_depth20.csv
```

The `book-csv` source uses the level-1 bid/ask midpoint as the paper-trading price. This path uses public market data only and does not need Binance API keys, private keys, or exchange account permissions.

## Local paper trading dashboard

Serve the local dashboard from a paper-trading run directory:

```bash
make paper-dashboard-v142 RUN_DIR=runs/paper_v142_book_csv_smoke BOOK_CSV=data/binance/BTCUSDT_ws_depth20.csv
```

Then open:

```text
http://127.0.0.1:8765/
```

The dashboard shows the latest public market price, top-of-book bid/ask, equity, drawdown, current paper positions, paper order events, decision reasons, recent trades, and rejected signals. It also draws a realtime K-line graph from recent paper-trading price snapshots. The K-line graph supports 1m, 5m, 15m, and 1h windows, horizontal drag/scroll navigation, Ctrl/Cmd + wheel zoom, a fit-to-latest control, and crosshair OHLC inspection. It overlays technical analysis:

- SMA 5/10/20
- EMA 12/26
- Bollinger Bands 20
- RSI 14
- MACD / signal / histogram
- support and resistance levels
- automatic pattern labels such as doji, hammer, shooting star, engulfing, range breakout/breakdown, SMA crosses, and RSI overbought/oversold

Its kill switch writes `kill_switch.json`; a running `paper-trade-v142` loop reads that file and force-closes open paper positions at the next valid market snapshot. This is still local paper trading only and does not submit exchange orders.

The public dashboard is read-only. Control actions are available at `/admin` and require HTTP Basic authentication configured through environment variables:

```bash
export PAPER_DASHBOARD_ADMIN_USER=admin
export PAPER_DASHBOARD_ADMIN_PASSWORD='change-me'
```

For long-running deployment, prefer `PAPER_DASHBOARD_ADMIN_PASSWORD_SHA256` instead of storing the plaintext password. Do not commit real dashboard credentials. Keep them in the deployment environment only.

## Validation commands

Focused checks:

```bash
make test-btcusdc-v193
make test-btcusdc-v142
make test-paper-trading-v142
make test-trade-replay-v142
```

Full verification:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Notes on data

Some historical runs depend on local Binance public-data downloads or generated research ledgers under `data/` and `runs/`. Those files are large and are excluded from git. Recreate them with the relevant `Makefile` target or command notes under `docs/`.

## License

No license file is included yet. Until one is added, treat this as source-available research code rather than open-source licensed software.
