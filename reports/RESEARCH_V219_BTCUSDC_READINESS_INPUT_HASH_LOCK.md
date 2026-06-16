# Research V219 BTCUSDC Readiness Input Hash Lock

## Decision

- Status: `real_money_launch_blocked`
- Allow real-money launch: `False`
- New lock: V204 readiness summaries must record SHA256 hashes for every evidence file they consume, and V206/CLI must verify those hashes still match.
- Current blocking reason: V204 is still `real_money_blocked`, V212 is not fresh with forward evidence, and V205/V209 execution provenance evidence is missing.

## Gate Checks

| Check | Result | Evidence |
|---|---:|---|
| V204 input hashes required | Yes | V204 records hashes for consumed evidence files |
| Missing input hash lock blocked | Yes | Tests reject otherwise-ready summaries without V219 hash evidence |
| Changed input hash blocked | Yes | Tests reject otherwise-ready summaries when an input file hash changes |
| CLI path protected | Yes | `real-trade-btcusdc` also recomputes and verifies input hashes |
| Strategy thresholds changed | No | V219 does not change the trading strategy |
| Entry/exit logic changed | No | V219 does not change trade selection |
| Leverage logic changed | No | V219 does not change leverage |
| Places live orders | No | V219 is a launch evidence gate only |

## Iteration Metrics

| Metric | V219 |
|---|---:|
| New backtest return improvement claimed | No |
| Requires V204 input SHA256 evidence | Yes |
| Blocks readiness summary when input evidence changes | Yes |
| Allow real-money launch | False |

## Interpretation

V219 closes an input-evidence drift loophole. A V204 readiness summary can no longer satisfy launch preflight if any evidence file it consumed has changed after the summary was generated.

This does not create trades, tune thresholds, or claim new profitability. Real-money use remains blocked until current forward monitoring, execution validation, provenance evidence, source provenance, and input hashes are all clean.
