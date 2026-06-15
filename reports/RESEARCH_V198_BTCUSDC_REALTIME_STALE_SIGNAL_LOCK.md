# Research V198 BTCUSDC Realtime Stale Signal Lock

## Decision

- Status: `realtime_stale_signal_lock_applied`
- Promote to live: `False`
- Historical optimization allowed: `False`
- Realtime default strategy mode: `realtime_safe`
- Max realtime signal age: `5.0` minutes
- Message: Realtime-safe paper trading now rejects stale, future-dated, wrong-symbol, or invalid-side signals before opening positions.

## Required Iteration Metrics

| Metric | V193 | V194 |
|---|---:|---:|
| Account return estimate | +3950.66% | +4044.70% |
| Improvement | - | +94.04 percentage points |
| Max drawdown | -30.20% | -30.20% |
| Positive months | 24/24 | 24/24 |
| Holdout return | +1386.21% | +1452.80% |
| Holdout months | 6/6 | 6/6 |

## Realtime Safety Rules

- V198 is an operational safety change, not a new strategy overlay.
- `realtime_safe` rejects signals older than `max_realtime_signal_age_minutes`.
- `realtime_safe` rejects future-dated signals.
- `realtime_safe` rejects wrong-symbol or invalid-side signals.
- `research_v142` keeps historical replay behavior for intentional research use.
- Snapshot logs include `rejected_signal_count` so skipped signals are visible.

## Interpretation

V197 stopped realtime paper trading from defaulting to historical high-leverage research sizing. V198 adds a second realtime guard: old historical signals cannot accidentally become fresh realtime entries. This reduces one practical overfitting-to-realtime failure path without changing historical strategy thresholds.

This is paper trading only. No live orders are placed, and this is not a live trading guarantee.

