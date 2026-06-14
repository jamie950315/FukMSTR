# Research V48 Results: BTCUSDC Full 1m Direct ML Probe

V48 tests whether the full available BTCUSDC public 1m bar history contains a direct, cost-aware linear signal after the transferred V26 rule failed on true BTCUSDC replay.

## Command

```bash
make btcusdc-full-1m-direct-ml-v48
```

Main run:

```text
runs/research_v48_btcusdc_full_1m_direct_ml_probe
```

## Data

| Item | Value |
|---|---:|
| Public BTCUSDC 1m bars | 1,279,409 |
| Date range | 2024-01-04 12:31 UTC through 2026-06-10 23:59 UTC |
| Feature count | 53 |
| Model | Ridge(alpha=10), standardized features |
| Cost | 8.5 bps round trip |
| Walk-forward | 365d train / 90d selector / 60d validation |
| Folds | 7 |

## Raw Horizon Summary

| Horizon minutes | Active folds | Passed folds | Validation total bps | Worst fold bps | Trades |
|---:|---:|---:|---:|---:|---:|
| 720 | 7 | 4 | -363.9278 | -3343.8237 | 261 |
| 30 | 2 | 1 | -426.6503 | -469.0004 | 44 |
| 240 | 7 | 3 | -1431.3240 | -2126.4401 | 295 |
| 15 | 5 | 2 | -4441.2664 | -2906.0499 | 684 |
| 1440 | 7 | 3 | -4906.2914 | -3332.8719 | 253 |
| 480 | 7 | 1 | -5277.3317 | -3718.0369 | 331 |
| 120 | 7 | 4 | -6816.7432 | -3759.3175 | 818 |
| 60 | 7 | 3 | -7239.4736 | -3340.2370 | 828 |

## Prequential Gate Summary

| Warmup folds | Active folds | Passed folds | Validation total bps | Worst active fold bps | Trades |
|---:|---:|---:|---:|---:|---:|
| 1 | 5 | 3 | -1374.0122 | -3343.8237 | 200 |
| 2 | 4 | 3 | -1374.0122 | -3343.8237 | 200 |
| 3 | 3 | 2 | -1846.7404 | -3343.8237 | 159 |
| 4 | 2 | 2 | +1497.0832 | +471.6927 | 103 |

## Conclusion

The direct Ridge probe finds weak long-horizon signal, strongest around 720 minutes, but it is not stable enough for promotion. The best raw horizon is still net negative, and the only positive prequential gate variant activates only two folds, which is too little evidence for the target.
