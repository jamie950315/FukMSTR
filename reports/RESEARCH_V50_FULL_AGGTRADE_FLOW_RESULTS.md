# Research V50 Results: BTCUSDC Full Available AggTrade Flow Probe

V50 tests whether full available BTCUSDC public aggTrade flow contains a more stable signal than V48/V49 1m kline direct-ML probes.

## Data

Input:

```text
data/binance_public/um/daily/aggTrades/BTCUSDC
```

Aggregated bars:

```text
runs/research_v50_btcusdc_full_aggtrade_flow_input/btcusdc_full_aggtrade_1m_flow_bars.csv
```

Summary:

| Item | Value |
|---|---:|
| aggTrade zip files | 889 |
| aggTrade rows | 259,997,196 |
| 1m flow bars | 1,278,095 |
| Date range | 2024-01-04 12:31 UTC through 2026-06-10 23:59 UTC |

Two corrupted downloaded zip files were found and redownloaded before aggregation:

```text
BTCUSDC-aggTrades-2024-03-30.zip
BTCUSDC-aggTrades-2024-04-18.zip
```

## Quick Flow Rule Probe

Output:

```text
runs/research_v50_btcusdc_full_aggtrade_flow_quick_probe
```

The quick probe tests flow momentum/reversal rules over:

```text
horizons: 240, 480, 720, 1440 minutes
lookbacks: 15, 30, 60, 120, 240, 480, 720, 1440 minutes
filters: abs_flow_imbalance, volume_ratio, range_bps
selection: calibration-only within each fold
cost: 8.5 bps
folds: 7 chronological folds
```

## Calibration-Selected Result

| Metric | Value |
|---|---:|
| Active folds | 7 |
| Passed folds | 3 |
| Validation total | -4960.7078 bps |
| Worst fold | -4794.8462 bps |
| Median fold | -214.3813 bps |
| Trades | 619 |

The calibration selector still fails out of sample.

## Validation Oracle Gap

| Metric | Value |
|---|---:|
| Oracle passed folds | 7 |
| Oracle validation total | +21910.1894 bps |
| Oracle worst fold | +1842.1082 bps |
| Oracle trades | 536 |

This confirms that profitable candidates exist in hindsight, but that is not tradable evidence.

## Prequential Selector Result

The best prequential result is all risk-off:

| Warmup | Rule | Active folds | Total |
|---:|---|---:|---:|
| 4 | prior_total | 0 | 0.0000 bps |

All active prequential variants were negative. The selector could not use prior folds to identify future winners.

## Fixed Policy Check

The best fixed policies are positive only when allowed to be active in few folds:

| Policy | Active folds | Total bps | Worst active fold bps |
|---|---:|---:|---:|
| `1440|720|flow_momentum|range_bps|0.9` | 3 | +5592.4117 | +1098.0124 |
| `720|240|flow_reversal|range_bps|0.94` | 4 | +3759.9648 | +168.0481 |

Among policies active in at least 5 folds, the best result is still not stable enough:

| Policy | Active folds | Total bps | Worst active fold bps |
|---|---:|---:|---:|
| `720|720|flow_reversal|range_bps|0.8` | 6 | +1719.8530 | -1283.0524 |
| `1440|120|flow_reversal|range_bps|0.6` | 7 | +1394.1101 | -2923.8539 |

## Conclusion

Full aggTrade flow improves the oracle opportunity set, but the non-oracle selectors still fail. V50 shows that the target is blocked by selection stability, not by absence of any hindsight-profitable flow candidates.
