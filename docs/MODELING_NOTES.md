# Modeling notes

## Target

The default label is future mid-price direction:

```text
future_return_bps = (future_mid - mid) / mid * 10000
```

Labels:

```text
up   =  1 if future_return_bps > threshold_bps
down = -1 if future_return_bps < -threshold_bps
flat =  0 otherwise
```

## Feature families

Core features:

- Mid price, spread, spread bps.
- L1 and multi-level microprice.
- Queue imbalance and cumulative depth imbalance.
- Depth ratio and VWAP pressure.
- Order-flow imbalance by level and cumulative levels.
- Depth-shape features: top concentration, tail imbalance, book width, depth per bps.
- Rolling row-window means, z-scores, momentum, and EWMA deltas.
- Optional rolling trade imbalance when trade prints are supplied.

## Validation

Use chronological validation. Random splits leak adjacent market state.

The package supports:

- Single chronological split through `train`.
- Grid search through `tune`.
- Embargoed walk-forward through `walk-forward`.
- Shuffled-label sanity check in walk-forward mode.
- Feature correlation diagnostics through `diagnostics`.
- Deterministic rule baselines through `rule-baselines`.

## Backtest meaning

Event PnL:

```text
pnl_bps = signal * future_return_bps - cost_bps * traded
```

Non-overlap mode keeps at most one trade per horizon window. This reduces the artifact of counting many overlapping half-second labels against the same future move.

Both modes are triage tools. They do not simulate queue priority, partial fills, market impact, maker/taker fee tiers, latency, or exchange matching.

## v0.3 research notes

The packaged Tardis 10-second, 1-bps experiments show:

- Strongest single-feature validation correlations come from L1 bid depth, bid size, top concentration, imbalance, and microprice deviation.
- Logistic models can show positive cost-adjusted PnL on a single chronological split at high edge thresholds.
- Low edge thresholds overtrade and degrade after costs.
- The next confidence step is walk-forward validation across more days and market regimes.
