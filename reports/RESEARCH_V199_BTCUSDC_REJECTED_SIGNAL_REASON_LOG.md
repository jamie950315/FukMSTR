# Research V199 BTCUSDC Rejected Signal Reason Log

## Decision

- Status: `rejected_signal_reason_log_applied`
- Promote to live: `False`
- Historical optimization allowed: `False`
- Realtime default strategy mode: `realtime_safe`
- Rejected signal log: `rejected_signals.csv`
- Message: Realtime-safe paper trading now records rejected signal reasons for auditability.

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

- V199 is an operational observability change, not a new strategy overlay.
- Every realtime-safe rejected signal is written with a reason.
- The log separates stale, future-dated, wrong-symbol, and invalid-side rejections.
- `summary.json` records the rejected-signal count and log path.
- `research_v142` keeps historical replay behavior for intentional research use.

## Interpretation

V198 prevented old historical signals from being used as realtime entries. V199 makes that guard observable. This matters before live use because a silent rejection count is not enough to diagnose whether signal production is late, future-dated, mismatched by symbol, or malformed.

This is paper trading only. No live orders are placed, and this is not a live trading guarantee.

