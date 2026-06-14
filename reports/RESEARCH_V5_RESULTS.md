# Superseded by Research V06

V06 found that this v05 result set included feature leakage from `future_best_bid` and `future_best_ask`. These columns were intended for taker bid/ask backtesting metadata and were accidentally eligible as model features. The v05 positive results are invalid as predictive evidence. Read `reports/RESEARCH_V6_RESULTS.md` first.

---

# Research V05 Results

V05 moves the project from mid-price research PnL toward a stricter execution simulation. The key new test is taker bid/ask entry and exit with non-overlap sampling and configurable latency.

## What changed

- Added `src/lob_microprice_lab/execution.py`.
  - `backtest_taker_bidask_non_overlapping`
  - `sweep_taker_bidask`
  - `robust_profit_gate`
- Added `src/lob_microprice_lab/ensemble.py`.
  - calibration-selected ensemble walk-forward
  - probability averaging across `logistic`, `hgb`, `et`, or any selected subset
  - train-only top-k feature selection by forward-return rank
- Added `src/lob_microprice_lab/rule_taker.py`.
  - deterministic rule walk-forward under the same taker bid/ask assumptions
  - used to check whether the previous imbalance rule survives stricter execution
- Added CLI commands:
  - `ensemble-walk-forward`
  - `rule-taker-walk-forward`
  - `backtest-taker`
  - `sweep-taker`
- Added tests: `tests/test_execution_v05.py`.
- Added config: `configs/real_h30_v05.yaml`.

## Execution model

Long signal:

```text
entry = best ask at t + latency
exit  = best bid at t + horizon
```

Short signal:

```text
entry = best bid at t + latency
exit  = best ask at t + horizon
```

This crosses spread on both entry and exit. It is more conservative than the v03/v04 mid-price backtest. It still omits queue position, partial fills, funding, exchange-specific fee tiers, market impact, and live latency distribution.

## Main result

The earlier H5/H10 signal does not survive stricter taker bid/ask execution. The first configuration that passes the bundled v05 single-sample research gate is a 30 second horizon ensemble using `logistic,hgb`, top 80 train-selected features, and calibration-selected edge thresholds restricted to `0.1,0.2,0.3,0.5,0.7`.

Command:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli ensemble-walk-forward \
  --book data/real_tardis/book_depth10_500ms.csv \
  --config configs/real_h30_v05.yaml \
  --out runs/research_v05_ensemble_h30_taker_no09 \
  --horizon-sec 30 \
  --threshold-bps 1 \
  --models logistic,hgb \
  --candidate-edges 0.1,0.2,0.3,0.5,0.7 \
  --cost-bps 1.5 \
  --latency-sec 0.5 \
  --stress-cost-bps-values 1.5,3.0 \
  --stress-latency-sec-values 0,0.5,1.0 \
  --folds 2 \
  --min-train-ratio 0.5 \
  --valid-ratio 0.15 \
  --calibration-ratio 0.2 \
  --top-k-features 80 \
  --min-calibration-trades 10 \
  --clean
```

Result:

| Metric | Value |
|---|---:|
| strict research pass | true |
| robust profit gate | true |
| OOF trades | 41 |
| OOF hit rate | 1.0000 |
| OOF mean net PnL | 4.4230 bps/trade |
| OOF total net PnL | 181.3427 bps |
| fold min valid trades | 20 |
| fold min valid mean net PnL | 3.8165 bps/trade |
| fold min bootstrap p05 mean PnL | 1.8532 bps/trade |

Fold details:

| fold | selected edge | trades | hit rate | mean net bps | total net bps | bootstrap p05 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.5 | 21 | 1.0000 | 5.0006 | 105.0128 | 1.8532 |
| 2 | 0.7 | 20 | 1.0000 | 3.8165 | 76.3298 | 1.9494 |

## Extended stress check

Additional stress was run after the primary experiment:

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli sweep-taker \
  --predictions runs/research_v05_ensemble_h30_taker_no09/oof_taker_backtest.csv \
  --out runs/research_v05_ensemble_h30_taker_no09/oof_taker_extreme_stress.csv \
  --horizon-sec 30 \
  --cost-bps-values 1.5,3.0,5.0 \
  --latency-sec-values 0,0.5,1.0,2.0 \
  --edge-thresholds 0.1,0.2,0.3,0.5,0.7
```

Best robust candidate in this extended grid:

| edge | cells | min trades | min mean net bps | min total net bps | pass |
|---:|---:|---:|---:|---:|---|
| 0.7 | 12 | 40 | 1.4461 | 57.8441 | true |

This means the same out-of-fold prediction set stayed positive across 1.5/3.0/5.0 bps costs and 0/0.5/1.0/2.0 second latency settings for edge threshold 0.7.

## Failed shorter horizons

| Run | Horizon | strict pass | robust gate | OOF trades | OOF mean net bps | OOF total net bps |
|---|---:|---|---|---:|---:|---:|
| ensemble H5 | 5s | false | false | 53 | -1.4115 | -74.8075 |
| ensemble H10 | 10s | false | false | 69 | -1.4427 | -99.5458 |
| ensemble H20 | 20s | false | true | 23 | 4.0887 | 94.0395 |
| ensemble H30 with 0.9 edge allowed | 30s | false | true | 37 | 5.1923 | 192.1144 |
| ensemble H30 no 0.9 edge | 30s | true | true | 41 | 4.4230 | 181.3427 |
| ensemble H30 no 0.9 edge, 3-fold | 30s | false | true | 64 | 4.7409 | 303.4157 |

The 3-fold H30 run failed only because the minimum fold trade count was 19, below the current hard gate of 20. Mean PnL and bootstrap lower bounds remained positive across folds.

## Deterministic rule control

The deterministic rule baseline does not survive the same taker bid/ask execution.

Command:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli rule-taker-walk-forward \
  --book data/real_tardis/book_depth10_500ms.csv \
  --config configs/real_h30_v05.yaml \
  --out runs/research_v05_rule_taker_h30 \
  --horizon-sec 30 \
  --threshold-bps 1 \
  --signal-thresholds 0,0.05,0.1,0.2,0.3,0.5,0.7 \
  --candidate-edges 0.5 \
  --cost-bps 1.5 \
  --latency-sec 0.5 \
  --stress-cost-bps-values 1.5,3.0 \
  --stress-latency-sec-values 0,0.5,1.0 \
  --folds 2 \
  --min-train-ratio 0.5 \
  --valid-ratio 0.15 \
  --calibration-ratio 0.2 \
  --min-calibration-trades 10 \
  --clean
```

Result:

| Metric | Value |
|---|---:|
| strict pass | false |
| robust gate | false |
| OOF trades | 50 |
| OOF mean net PnL | -0.3887 bps/trade |
| OOF total net PnL | -19.4337 bps |

Interpretation: the learned ensemble is doing something different from the simple imbalance/microprice rule set under this sample and execution model.

## Current status

V05 finds a single-sample research candidate that passes the local strict gate. This is not enough to call it stable profit. The evidence is stronger than v04 because it survives taker bid/ask execution, latency, higher cost stress, calibration-only edge selection, and a deterministic rule control. The evidence is still limited because it uses one Deribit BTC-PERPETUAL sample day, no trade prints, no queue-position model, and no multi-day regime coverage.

Promotion status:

```text
single-sample research gate: passed
multi-day stability gate: not tested
live deployment gate: failed by missing evidence
```

## Next research targets

1. Add true multi-day Tardis download support and require at least 20 independent days.
2. Add Tardis trade prints and aggressor-flow features.
3. Add bid/ask execution with simulated maker queue position and partial fills.
4. Add per-exchange fee tier and Deribit/Binance futures contract mechanics.
5. Add label-shuffle and block-bootstrap null controls for the ensemble path.
6. Promote only if H30 candidate survives multi-day walk-forward and beats rule baselines on every tested regime bucket.
