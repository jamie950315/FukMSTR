# Roadmap

## Phase 1: Stabilize research baseline

- Keep the CSV data contract stable.
- Add tests for missing levels, no trades, flat-only labels, and crossed books.
- Add dataset hash, config hash, package versions, and runtime to every run manifest.
- Refactor `features.py` to build large feature blocks with `pd.concat` to reduce pandas fragmentation.

## Phase 2: Improve real-data capture

Implemented:

- Tardis public L2 sample downloader and converter.
- Binance public spot REST depth polling.
- Binance spot local-book WebSocket collector with REST snapshot seeding and sequence-gap checks.

Next:

- Add Binance futures diff-depth capture.
- Add Tardis trade-print conversion and align aggressor-side trades with L2 snapshots.
- Add replay tests using frozen fixture files.
- Add dataset manifests with exchange, symbol, time range, row count, and hash.

## Phase 3: Stronger validation

Implemented:

- Single chronological split.
- Edge-threshold sweep.
- Event and non-overlap backtests.
- Embargoed walk-forward scaffold.
- Shuffled-label sanity check.

Next:

- Run walk-forward across multiple days and symbols.
- Add latency-shifted entry prices.
- Add non-overlapping event sampling before training.
- Add blocked bootstrap confidence intervals for PnL and hit rate.

## Phase 4: Better models

Current:

- Logistic regression.
- HistGradientBoosting.
- RandomForest.
- ExtraTrees.

Next:

- Optional LightGBM or XGBoost backend.
- Probability calibration tuned on validation PnL.
- Temporal CNN or DeepLOB-style model for raw LOB sequences.
- Model comparison with stable feature subsets and fixed seeds.

## Phase 5: Execution research

Next:

- Taker execution by walking book depth.
- Maker queue simulation.
- Latency and cancellation simulation.
- Inventory and risk limits.
- Keep live order placement outside this research package.
