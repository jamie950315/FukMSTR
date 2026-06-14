# Research V49 Quick Probe Results: BTCUSDC Nonlinear Direct ML

V49 quick probe checks whether a lightweight nonlinear tree model improves the weak long-horizon signal found in V48.

## Context

V48 found the strongest direct 1m-bar Ridge signal at a 720-minute horizon, but the result remained net negative:

```text
best raw V48 horizon: 720 minutes
validation total: -363.9278 bps
passed folds: 4 of 7
worst fold: -3343.8237 bps
```

## HGB attempt

A full HistGradientBoosting probe and a sampled HistGradientBoosting probe were attempted, but both were too slow for practical repeated research on the full BTCUSDC 1m dataset in this environment. They were stopped before producing fold-level results.

## ExtraTrees quick probe

The follow-up quick probe used:

```text
model: ExtraTreesRegressor
horizon: 720 minutes
features: compact 20-feature 1m bar set
training: fixed 80,000-row sample per fold
validation: full validation windows
folds: latest 4 walk-forward folds
cost: 8.5 bps
```

Output:

```text
runs/research_v49_btcusdc_extratrees_quick_probe/extratrees_720_recent4_folds.csv
```

## Result

| Fold | Validation trades | Validation total bps | Validation mean bps |
|---:|---:|---:|---:|
| 1 | 52 | -775.1315 | -14.9064 |
| 2 | 30 | -427.8305 | -14.2610 |
| 3 | 42 | +401.7252 | +9.5649 |
| 4 | 27 | -363.2858 | -13.4550 |

Summary:

| Metric | Value |
|---|---:|
| Active folds | 4 |
| Passed folds | 1 |
| Validation total | -1164.5226 bps |
| Worst fold | -775.1315 bps |
| Trades | 151 |

## Conclusion

The nonlinear quick probe does not improve the target. It confirms that the V48 weak signal is not easily rescued by a shallow tree ensemble on compact BTCUSDC 1m features.
