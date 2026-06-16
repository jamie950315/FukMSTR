# Research V217 BTCUSDC Launch Execution Provenance Lock

## Decision

- Status: `real_money_launch_blocked`
- Allow real-money launch: `False`
- New lock: V206 script and V207 CLI preflight require V216 execution and signal provenance evidence inside the V204 readiness summary.
- Current blocking reason: V204 is still `real_money_blocked`, V212 is not fresh with forward evidence, and V205/V209 execution provenance evidence is missing.

## Gate Checks

| Check | Result | Evidence |
|---|---:|---|
| V204 readiness required | Blocked | V204 failed checks include forward evidence, forward freshness, execution validation, fill evidence, execution provenance, signal provenance, and slippage |
| V212 freshness required | Blocked | V212 data is current but forward evidence is unavailable because new signal count is 0 |
| V214 public data required | Present | V214 reports latest completed UTC day is published and local files are present |
| V216 execution provenance required | Blocked | V204 summary reports missing fill/provenance/slippage evidence |
| Legacy ready summary without V216 blocked | Yes | Tests reject a V204 summary that says ready but lacks V216 execution provenance evidence |
| CLI path protected | Yes | `real-trade-btcusdc` also requires V216 evidence |

## Iteration Metrics

| Metric | V217 |
|---|---:|
| Strategy thresholds changed | No |
| Entry/exit logic changed | No |
| Leverage logic changed | No |
| New backtest return improvement claimed | No |
| Places live orders | No |
| Requires V216 execution provenance evidence | Yes |
| Allow real-money launch | False |

## Interpretation

V217 closes a final launch-preflight stale-summary loophole. A historical or manually edited V204 summary that says `real_money_ready` is no longer enough to pass launch preflight unless it also proves that V216 execution and signal provenance evidence passed.

This does not create trades, tune thresholds, or claim new profitability. Real-money use remains blocked until current forward monitoring, execution validation, and provenance evidence are all clean.
