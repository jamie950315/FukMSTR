# Research V223 BTCUSDC Strategy Manifest Lock

## Decision

- Status: `real_money_launch_blocked`
- Allow real-money launch: `False`
- New lock: V204 must record a fixed strategy manifest path and hash; V206 and the CLI must verify the current manifest still matches.
- Official online/paper iteration: `V193`
- Current blocking reason: V204 is still `real_money_blocked`, V212 has no fresh forward evidence, and V205 execution evidence is missing or incomplete.

## Gate Checks

| Check | Result | Evidence |
|---|---:|---|
| Fixed strategy manifest added | Yes | `configs/btcusdc_v223_promoted_strategy_manifest.json` |
| Fixed manifest identifies V193 | Yes | `official_online_iteration=V193` |
| V204 requires manifest hash | Yes | Readiness gate blocks summaries missing `strategy_manifest_hash_clean` |
| V206 requires manifest hash | Yes | Launch preflight blocks ready summaries without a matching manifest hash |
| CLI requires manifest hash | Yes | `real-trade-btcusdc` preflight blocks ready summaries without a matching manifest hash |
| Strategy thresholds changed | No | V223 does not change the trading strategy |
| Entry/exit logic changed | No | V223 does not change trade selection |
| Leverage logic changed | No | V223 does not change leverage |
| Places live orders | No | V223 is an evidence provenance gate only |

## Iteration Metrics

| Metric | V223 |
|---|---:|
| New backtest return improvement claimed | No |
| Requires fixed strategy manifest hash | Yes |
| Blocks missing or changed manifest before launch | Yes |
| Allow real-money launch | False |

## Interpretation

V223 closes a strategy-drift loophole. A readiness summary can no longer be treated as launchable unless it names and hashes the fixed strategy manifest, and the launch preflight verifies the manifest still matches.

This does not create trades, tune thresholds, or claim new profitability. Real-money use remains blocked until current forward monitoring, recent execution validation, provenance evidence, source hashes, input hashes, and the fixed manifest are all clean.
