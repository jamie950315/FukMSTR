# Research V215 BTCUSDC Launch Public Data Lock

## Decision

- Status: `real_money_launch_blocked`
- Allow real-money launch: `False`
- New lock: V206 script and V207 CLI preflight require V214 public-data availability evidence inside the V204 readiness summary.
- Current blocking reason: V204 is still `real_money_blocked`, and V212 is `forward_fresh_no_signal`.

## Gate Checks

| Check | Result | Evidence |
|---|---:|---|
| V204 readiness required | Blocked | V204 failed checks include forward evidence, forward freshness, execution validation, and overfitting audit status |
| V212 freshness required | Blocked | V212 data is current but forward evidence is unavailable because new signal count is 0 |
| V214 public data required | Present | V214 reports latest completed UTC day is published and local files are present |
| Legacy ready summary without V214 blocked | Yes | Tests reject a V204 summary that says ready but lacks V214 public-data evidence |
| CLI path protected | Yes | `real-trade-btcusdc` also requires V214 public-data evidence |

## Iteration Metrics

| Metric | V215 |
|---|---:|
| Strategy thresholds changed | No |
| Entry/exit logic changed | No |
| Leverage logic changed | No |
| New backtest return improvement claimed | No |
| Places live orders | No |
| Requires V214 public-data evidence | Yes |
| Allow real-money launch | False |

## Interpretation

V215 closes a stale-summary loophole. A historical or manually edited V204 summary that says `real_money_ready` is no longer enough to pass launch preflight unless it also proves that V214 public-data availability passed.

This does not create trades, tune thresholds, or claim new profitability. Real-money use remains blocked until current forward monitoring and execution validation provide enough evidence.
