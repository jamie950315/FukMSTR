# V143 Market Emotion Trend Audit Plan

## Goal

Check whether adding prior-only market emotion and trend context improves the fixed V142 BTCUSDC candidate without changing the V142 trade list first.

## Completion Criteria

- V143 joins V142 selected trades with V119 live feature context by timestamp.
- V143 derives only prior-known features: trend-follow strength, range-position alignment, and probability/emotion heat.
- V143 evaluates baseline, filters, and sizing overlays using a selector period and a later holdout period.
- V143 writes reproducible CSV/JSON outputs plus a report with a clear pass/fail decision.
- Tests cover feature construction, month accounting, and selector-only candidate selection.
- Relevant V143 test target, full pytest, and package build pass.

## Implementation Notes

- Do not modify V142 behavior.
- Do not tune thresholds on the holdout period.
- Treat this as a research audit, not live trading proof.
