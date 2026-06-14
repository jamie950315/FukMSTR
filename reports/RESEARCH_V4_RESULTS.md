# Research V04 Results

This version adds conservative stability tooling rather than claiming deployment-ready profitability.

## What changed

- Added latency-aware non-overlap backtesting in `src/lob_microprice_lab/stress.py`.
- Added cost/latency/edge stress sweeps with `lob-microprice-lab stress`.
- Added robust grid gate requiring a single edge threshold to remain positive across all tested cost and latency cells.
- Added block-bootstrap confidence intervals over trade PnL.
- Added regime breakdown by edge confidence and any feature columns carried into prediction CSVs.
- Added adaptive walk-forward in `src/lob_microprice_lab/adaptive.py`: each fold selects the edge threshold only from a past calibration window, then applies that fixed threshold to the future validation fold.
- Prediction CSVs now carry key market-state columns such as spread, imbalance, OFI, microprice deviation, and rolling volatility when available.

## Main finding

The previous H10 OOF result still shows a small positive result under 1.5 bps cost and zero latency, but it does not pass the new robust grid gate. The signal degrades under 0.5-1.0 seconds of latency or 3.0 bps cost.

## V04 stress test on previous H10 OOF

Command:

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli stress \
  --predictions runs/research_v3_walk_forward_h10_base_2fold/oof_predictions.csv \
  --out runs/research_v4_stress_h10_old_oof \
  --horizon-sec 10 \
  --edge-thresholds 0.3,0.5,0.7,0.9 \
  --cost-bps-values 1.5,3.0 \
  --latency-sec-values 0,0.5,1.0 \
  --clean
```

Best point result:

| cost_bps | latency_sec | edge | trades | hit_rate | mean_net_bps | total_net_bps |
|---:|---:|---:|---:|---:|---:|---:|
| 1.5 | 0.0 | 0.5 | 68 | 0.4853 | 0.4246 | 28.8759 |

Robust grid gate:

```json
{
  "passed": false,
  "best_candidate": {
    "edge_threshold": 0.5,
    "cells": 6,
    "positive_mean_cells": 2,
    "positive_total_cells": 2,
    "min_trades": 67.0,
    "min_mean_net_pnl_bps": -1.6746087362186381,
    "median_mean_net_pnl_bps": -0.6249813029688233,
    "min_total_net_pnl_bps": -112.19878532664876,
    "passed": false
  }
}
```

Interpretation: this is a narrow zero-latency edge, not a stable profit candidate.

## Adaptive walk-forward results

Adaptive walk-forward avoids selecting the edge threshold from the reported validation fold. It uses a past calibration window inside each train fold.

| Run | Latency | Min calibration trades | OOF trades | OOF mean net bps | OOF total net bps | Bootstrap p05 min | Pass |
|---|---:|---:|---:|---:|---:|---:|---|
| H10 | 0.0s | 5 | 7 | 0.5352 | 3.7464 | -1.1214 | false |
| H10 | 0.5s | 5 | 7 | -0.1452 | -1.0161 | -1.1214 | false |
| H10 | 0.0s | 20 | 90 | 0.0073 | 0.6545 | -0.8645 | false |
| H5 | 0.0s | 20 | 47 | 0.1616 | 7.5970 | -1.3411 | false |
| H5 | 0.5s | 20 | 47 | -0.3702 | -17.3977 | -1.2545 | false |
| H15 | 0.0s | 20 | 68 | -1.4183 | -96.4468 | -5.2830 | false |

The H5 zero-latency result has both validation folds positive on mean PnL, but bootstrap lower confidence remains negative and it fails under 0.5s latency. It should stay in research mode.

## Current promotion criteria

A configuration should be promoted only when all are true:

1. Adaptive walk-forward `strict_research_pass == true`.
2. Robust grid gate passes across at least two costs and two latency settings.
3. Bootstrap p05 of mean trade PnL is positive in every fold.
4. It beats deterministic rule baselines on strict non-overlap PnL.
5. It is verified on multiple independent days and at least two symbols.

Current status: no configuration in this bundled single-day sample clears that bar.

## Next research targets

1. Add Tardis trade prints and align aggressor flow with L2 updates.
2. Run multi-day Deribit/Binance/OKX walk-forward to separate true signal from sample artifact.
3. Add latency-shifted entry/exit based on best bid/ask instead of mid-price.
4. Add queue-position and maker/taker fill simulation.
5. Add exchange fee tiers, funding, liquidation-event regimes, and volatility halts.
6. Replace single-model probability with calibration + model ensemble only after adaptive thresholding becomes stable.
