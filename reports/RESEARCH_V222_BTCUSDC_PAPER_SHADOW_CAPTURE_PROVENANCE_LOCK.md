# Research V222 BTCUSDC Paper-Shadow Capture Provenance Lock

## Decision

- Status: `real_money_launch_blocked`
- Allow real-money launch: `False`
- New lock: `paper_shadow_live` fills must be backed by a matching V210 capture summary.
- Current blocking reason: V204 is still `real_money_blocked`, V212 has no fresh forward evidence, and V205 execution evidence is missing or incomplete.

## Gate Checks

| Check | Result | Evidence |
|---|---:|---|
| V205 rejects paper-shadow fills without capture summary | Yes | Tests reject clean-looking `paper_shadow_live` rows without V210 summary |
| V205 verifies capture ID and evidence source | Yes | Capture summary must match fill audit fields |
| V205 verifies no live orders were placed | Yes | Capture config and decision must both report `places_live_orders=False` |
| V204 requires V222 check | Yes | Readiness gate blocks summaries missing `paper_shadow_capture_summary_clean` |
| V206/CLI require V222 check | Yes | Launch preflight includes the V222 check in execution provenance |
| Strategy thresholds changed | No | V222 does not change the trading strategy |
| Entry/exit logic changed | No | V222 does not change trade selection |
| Leverage logic changed | No | V222 does not change leverage |
| Places live orders | No | V222 is an evidence provenance gate only |

## Iteration Metrics

| Metric | V222 |
|---|---:|
| New backtest return improvement claimed | No |
| Requires V210 capture summary for paper-shadow fills | Yes |
| Blocks hand-built paper-shadow fill CSV without capture summary | Yes |
| Allow real-money launch | False |

## Interpretation

V222 closes a paper-shadow evidence loophole. A clean-looking fill CSV is no longer enough for `paper_shadow_live` execution evidence; it must be tied to a V210 capture summary that says how the rows were produced and confirms no live orders were placed.

This does not create trades, tune thresholds, or claim new profitability. Real-money use remains blocked until current forward monitoring, recent execution validation, provenance evidence, source hashes, and input hashes are all clean.
