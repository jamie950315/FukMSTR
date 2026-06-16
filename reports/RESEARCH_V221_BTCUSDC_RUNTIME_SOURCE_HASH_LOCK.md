# Research V221 BTCUSDC Runtime Source Hash Lock

## Decision

- Status: `real_money_launch_blocked`
- Allow real-money launch: `False`
- New lock: source provenance is tied to runtime source file hashes, not only full repository `HEAD`.
- Current blocking reason: V204 is still `real_money_blocked`, V212 has no fresh forward evidence, and V205 execution evidence is missing or not recent enough.

## Gate Checks

| Check | Result | Evidence |
|---|---:|---|
| V204 records runtime source hash | Yes | V204 includes `readiness_runtime_source_hash` |
| Missing runtime hash blocked | Yes | V206 requires `requires_readiness_runtime_source_hash` and matching evidence |
| Report-only commit accepted when runtime hash matches | Yes | Tests allow ancestor source commit with unchanged runtime hash |
| Runtime code change blocked | Yes | Tests reject changed runtime hash |
| CLI path protected | Yes | `real-trade-btcusdc` uses the same runtime hash preflight helper |
| Strategy thresholds changed | No | V221 does not change the trading strategy |
| Entry/exit logic changed | No | V221 does not change trade selection |
| Leverage logic changed | No | V221 does not change leverage |
| Places live orders | No | V221 is a source provenance gate only |

## Iteration Metrics

| Metric | V221 |
|---|---:|
| New backtest return improvement claimed | No |
| Requires runtime source hash | Yes |
| Allows report-only commit without false stale source failure | Yes |
| Blocks changed runtime source hash | Yes |
| Allow real-money launch | False |

## Interpretation

V221 fixes an operational provenance problem. Evidence-only report commits no longer make otherwise unchanged runtime code look stale, but any runtime source change still invalidates prior readiness evidence.

This does not create trades, tune thresholds, or claim new profitability. Real-money use remains blocked until current forward monitoring, recent execution validation, provenance evidence, source hashes, and input hashes are all clean.
