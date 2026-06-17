# Research V224 BTCUSDC Forward-Freeze Manifest Lock

## Decision

- Status: `real_money_launch_blocked`
- Allow real-money launch: `False`
- New lock: V196 must use a fixed forward-freeze manifest, and V204/V206/CLI must carry and verify its hash.
- Current blocking reason: V204 is still `real_money_blocked`, V212 has no fresh forward evidence, and V205 execution evidence is missing or incomplete.

## Gate Checks

| Check | Result | Evidence |
|---|---:|---|
| Fixed forward-freeze manifest added | Yes | `configs/btcusdc_v224_forward_freeze_manifest.json` |
| V196 requires manifest hash | Yes | Forward evidence is unavailable without `forward_freeze_manifest_clean` |
| V204 requires manifest hash | Yes | Readiness gate blocks forward evidence missing freeze-manifest provenance |
| V206 requires manifest hash | Yes | Launch preflight blocks ready summaries without a matching freeze manifest |
| CLI requires manifest hash | Yes | `real-trade-btcusdc` preflight uses the same check as V206 |
| Strategy thresholds changed | No | V224 does not change the trading strategy |
| Entry/exit logic changed | No | V224 does not change trade selection |
| Leverage logic changed | No | V224 does not change leverage |
| Places live orders | No | V224 is an evidence provenance gate only |

## Iteration Metrics

| Metric | V224 |
|---|---:|
| New backtest return improvement claimed | No |
| Requires fixed forward-freeze manifest hash | Yes |
| Blocks missing or changed freeze manifest before launch | Yes |
| Allow real-money launch | False |

## Interpretation

V224 closes a forward-monitoring overfitting loophole. The freeze timestamp can no longer be silently changed after seeing more data and still be treated as the same forward-validation protocol.

This does not create trades, tune thresholds, or claim new profitability. Real-money use remains blocked until current forward monitoring, recent execution validation, provenance evidence, source hashes, input hashes, strategy manifest, and forward-freeze manifest are all clean.
