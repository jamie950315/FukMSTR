# Research V197 BTCUSDC Realtime Overfit Lock

## Decision

- Status: `realtime_overfit_lock_applied`
- Promote to live: `False`
- Historical optimization allowed: `False`
- Realtime default strategy mode: `realtime_safe`
- Realtime safe leverage: `1.0x`
- Research replay mode: `research_v142`
- High-confidence rescue 5x default: `False`
- Message: Realtime paper-trading no longer defaults to the historical V142 high-confidence rescue 5x path.

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

- V197 is an operational safety change, not a new strategy overlay.
- The realtime/paper-trading CLI defaults to `realtime_safe`.
- `realtime_safe` uses `1.0x` leverage and disables the historical high-confidence rescue `5x` path.
- The historical V142 leverage behavior is still available only through explicit `--strategy-mode research_v142`.
- The generated `paper_config.json` records the selected strategy mode for auditability.

## Interpretation

V195 found overfitting risk in the late historical optimization path. V196 froze historical optimization and required new forward data before any validation claim. V197 applies that risk posture to the realtime entrypoint by making conservative sizing the default and forcing research leverage to be opt-in.

This is paper trading only. No live orders are placed, and this is not a live trading guarantee.

