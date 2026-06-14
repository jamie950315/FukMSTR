# Research V06 Results

V06 focused on 30 seconds and longer prediction windows. The main outcome is a leakage audit and a stricter long-window research workflow.

## Critical correction

V06 found that prior v05/v06 candidate runs accidentally allowed future execution columns into the model feature matrix:

```text
future_best_bid
future_best_ask
```

Those columns were added for bid/ask taker backtesting and should only be metadata. They are now excluded by `select_feature_columns()` through both explicit target-column exclusion and a `future_` prefix guard.

Impact: the v05 H30 positive result and the early v06 H45 positive results are invalid as model-performance evidence. They remain useful only as audit artifacts.

## Code changes

- Fixed leakage in `src/lob_microprice_lab/models.py`.
  - `TARGET_COLUMNS` now includes `future_best_bid` and `future_best_ask`.
  - `select_feature_columns()` now rejects every column starting with `future_`.
- Added stationary-only feature mode in `src/lob_microprice_lab/ensemble.py`.
  - `--stationary-only` removes raw absolute price features such as `mid`, `best_bid`, `best_ask`, and absolute `microprice_lN` values.
  - It keeps bps-normalized distances, returns, volatility, imbalance, OFI, and depth-shape features.
- Added `src/lob_microprice_lab/long_horizon.py`.
  - `long-horizon-sweep`
  - `summarize-long-runs`
  - v06 long-window gate for 30s+ non-overlap experiments.
- Added tests:
  - future execution columns are excluded from model features.
  - stationary filter drops absolute price features.
  - long-window gate and summarizer behavior.
- Added configs:
  - `configs/real_h30_v06_long.yaml`
  - `configs/real_h45_v06_long.yaml`

## Long-window gate

The v06 long-window gate is designed for 30s+ windows where non-overlapping trades are naturally sparse. Current default thresholds:

```json
{
  "min_fold_trades": 10,
  "min_oof_trades": 30,
  "min_fold_mean_net_bps": 0.0,
  "min_fold_bootstrap_p05_bps": 0.0,
  "min_oof_mean_net_bps": 0.0,
  "min_oof_hit_rate": 0.55,
  "require_robust_gate": true,
  "min_robust_mean_net_bps": 0.0,
  "min_robust_total_net_bps": 0.0
}
```

This gate is for research triage. It is not a live-trading promotion gate.

## Leak-free experiments run in v06

All leak-free experiments below use:

```text
book: data/real_tardis/book_depth10_500ms.csv
instrument: Deribit BTC-PERPETUAL bundled single-day sample
execution: taker bid/ask, non-overlap
cost: 1.5 bps
latency: 0.5s
folds: chronological 3-fold unless noted
candidate edge thresholds: 0.1,0.2,0.3,0.5,0.7
stress grid: cost 1.5/3.0/5.0 bps x latency 0/0.5/1.0/2.0s
```

| Run | Horizon | Stationary only | OOF trades | OOF hit rate | OOF mean net bps | OOF total net bps | Robust gate | v06 gate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `research_v06_leakfree_stationary_logistic_h30_3fold_top80` | 30s | true | 50 | 0.4800 | -0.1503 | -7.5140 | false | false |
| `research_v06_leakfree_stationary_logistic_h45_3fold_top80` | 45s | true | 36 | 0.4444 | -0.9439 | -33.9818 | false | false |
| `research_v06_leakfree_nonstationary_logistic_h45_3fold_top80` | 45s | false | 35 | 0.4857 | -0.5868 | -20.5396 | false | false |

Best leak-free run by v06 rank score:

```text
research_v06_leakfree_stationary_logistic_h30_3fold_top80
OOF trades: 50
OOF mean net PnL: -0.1503 bps/trade
OOF total net PnL: -7.5140 bps
OOF hit rate: 0.4800
v06 long-window gate: false
```

## Pre-fix audit results

Before the leakage fix, the best early v06 candidate was `research_v06_stationary_logistic_h45_3fold_top80`:

```text
OOF trades: 35
OOF mean net PnL: 6.0704 bps/trade
OOF total net PnL: 212.4638 bps
v06 long-window gate: true
```

This run is invalid because feature selection included future execution columns. A minimal evidence file is retained at `runs/archive_pre_v06_leakfix_evidence/selected_features_with_future_leak.csv`, showing `future_best_bid` and `future_best_ask` in the selected features.

## Current conclusion

After removing future-column leakage, the tested 30s and 45s logistic candidates do not have positive net expectancy on the bundled single-day Deribit sample under taker bid/ask execution, 0.5s latency, and 1.5 bps cost.

Current promotion status:

```text
single-day leak-free long-window gate: failed
multi-day stability gate: not tested
live deployment gate: failed by evidence
```

The most valuable progress in v06 is methodological: the framework now catches a serious class of leakage, can enforce stationary-only features, and can rank 30s+ candidates with a long-window gate.

## Next research actions

1. Re-run `long-horizon-sweep` on leak-free stationary-only features over 30/45/60/90s using more model sets once local compute time allows.
2. Add trade-print features; current bundled Tardis sample has no trade file, so aggressor-flow features are zeros.
3. Add multi-day Tardis/Binance futures data and require at least 20 independent days.
4. Add null controls that retrain with block-shuffled labels, not just post-hoc PnL randomization.
5. Add maker/queue/partial-fill modeling only after leak-free taker candidates become positive.
6. Treat archived v05 positive outputs as invalidated audit artifacts.

## Archive layout

Minimal pre-fix leakage evidence is stored under:

```text
runs/archive_pre_v06_leakfix_evidence/
```

Leak-free v06 runs are stored under:

```text
runs/research_v06_leakfree_stationary_logistic_h30_3fold_top80/
runs/research_v06_leakfree_stationary_logistic_h45_3fold_top80/
runs/research_v06_leakfree_nonstationary_logistic_h45_3fold_top80/
runs/research_v06_leakfree_summary/
```
