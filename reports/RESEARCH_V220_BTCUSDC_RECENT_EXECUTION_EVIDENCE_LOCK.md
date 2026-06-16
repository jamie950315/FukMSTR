# Research V220 BTCUSDC Recent Execution Evidence Lock

## Decision

- Status: `real_money_launch_blocked`
- Allow real-money launch: `False`
- New lock: execution evidence must be recent, not merely clean-looking.
- Current blocking reason: V204 is still `real_money_blocked`, V212 has no fresh forward evidence, and V205 execution evidence is missing or not recent enough.

## Gate Checks

| Check | Result | Evidence |
|---|---:|---|
| V205 rejects stale clean-looking fills | Yes | Tests reject old fills even when fields, provenance, slippage, and kill switch are clean |
| V204 requires recent execution evidence | Yes | V204 blocks legacy execution summaries without `recent_execution_evidence_clean` |
| V206 requires V220 evidence | Yes | V206 blocks legacy ready summaries without recent execution evidence |
| CLI path protected | Yes | `real-trade-btcusdc` uses the same V206 preflight helper |
| Strategy thresholds changed | No | V220 does not change the trading strategy |
| Entry/exit logic changed | No | V220 does not change trade selection |
| Leverage logic changed | No | V220 does not change leverage |
| Places live orders | No | V220 is an execution evidence gate only |

## Iteration Metrics

| Metric | V220 |
|---|---:|
| New backtest return improvement claimed | No |
| Max execution evidence age | 7 days |
| Requires recent execution evidence | Yes |
| Blocks stale execution evidence | Yes |
| Allow real-money launch | False |

## Interpretation

V220 closes an execution-evidence age loophole. A set of old fills can no longer satisfy the real-money readiness chain just because the rows look complete.

This does not create trades, tune thresholds, or claim new profitability. Real-money use remains blocked until current forward monitoring, recent execution validation, provenance evidence, source provenance, and input hashes are all clean.
