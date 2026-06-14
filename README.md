# FukMSTR

BTCUSDC short-term trading research, replay, and paper-trading tools.

This repository is a research workspace for testing short-horizon BTCUSDC signals, leverage rules, and historical replay behavior. It does not place live orders, does not connect to private exchange accounts, and should not be treated as a live trading guarantee.

## Current status

The latest working branch in this handoff is V142:

- BTCUSDC historical trade replay page
- Side backfill from the V119 signal reference when older account-path ledgers omit `signal`
- V142 paper-trading MVP with public Binance ticker support, CSV replay, synthetic demo data, and local dashboard output
- High-confidence rescue 5x leverage path with drawdown throttling

The generated replay data currently confirms that historical replay has no missing side labels:

```text
trades: 645
long: 513
short: 132
side = n/a: 0
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

## V142 replay

Generate the historical replay page:

```bash
make trade-replay-v142-page
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

## V142 paper trading demo

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
runs/paper_v142_demo/summary.json
```

The paper-trading tool is local simulation only. It records events and hypothetical trades but does not submit orders.

## Validation commands

Focused V142 checks:

```bash
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
