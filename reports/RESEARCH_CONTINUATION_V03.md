# Research Continuation v0.3.0

## Scope

This iteration extends the short-horizon limit-order-book research package beyond the v0.2 real-data baseline. The work focuses on richer microstructure features, stricter validation tools, rule baselines, feature diagnostics, feature-family ablation, and safer public-data capture.

## Added system capabilities

- Richer LOB features in `features.py`: Cont-style order-flow imbalance, depth-shape features, multi-level microprice, cumulative depth ratios, rolling row-window means, momentum, z-scores, and EWMA deltas.
- Expanded model tooling in `models.py`: logistic regression, HistGradientBoosting, RandomForest, ExtraTrees, probability metrics, expected calibration error, and feature-importance export.
- Stronger evaluation in `backtest.py` and `validation.py`: event-level backtest, non-overlapping horizon backtest, edge-threshold sweep, embargoed walk-forward validation, and optional shuffled-label sanity check.
- New research commands: `profile`, `feature-scan`, `diagnostics`, `correlations`, `rule-baselines`, `ablate-features`, and `collect-binance-ws`.

## Dataset used for packaged v3 runs

- Source: Tardis public Deribit `BTC-PERPETUAL` L2 sample already converted in v0.2.
- Local file: `data/real_tardis/book_depth10_500ms.csv`.
- Rows: 10,000 book snapshots.
- Depth: top 10 levels.
- Median sample step: about 0.504 seconds.
- Time range: `2020-04-01 00:00:00.245000+00:00` to `2020-04-01 01:24:57.338000+00:00`.
- Trades: no trade file packaged, so trade-derived features are zero-filled.

## Market profile

`runs/research_profile/` profiles the full 10,000-row file.

| Metric | Value |
|---|---:|
| rows_features | 10000 |
| feature_count with full config | 364 |
| median_step_sec | 0.504 |
| mid_move_rate | 0.1206 |
| up_move_rate | 0.0597 |
| down_move_rate | 0.0609 |
| median spread bps | 0.792299 |
| mean one-step abs return bps | 0.338382 |

## Feature diagnostics

`runs/research_v3_diagnostics_h10/` uses the full 10,000-row Tardis book snapshot file with the advanced 10-second, 1-bps config.

| Feature | Validation Spearman | Validation sign accuracy |
|---|---:|---:|
| `bid_sz_l1_log` | 0.346883 | 0.439712 |
| `bid_depth_l1` | 0.346883 | 0.439712 |
| `bid_top_concentration_l10` | 0.338725 | 0.439712 |
| `top_concentration_gap_l10` | 0.332290 | 0.711458 |
| `imbalance_l1` | 0.322081 | 0.701860 |
| `microprice_dev_bps` | 0.321596 | 0.701860 |

Liquidity-side pressure, L1/L3 imbalance, microprice deviation, and depth concentration are the strongest single-feature signals in this one sample.

## Single chronological split, H10 base model

`runs/research_v3_base_h10_single/` trains a 10-second, 1-bps logistic baseline with 264 features.

| Metric | Value |
|---|---:|
| rows_total | 9980 |
| accuracy | 0.438210 |
| balanced_accuracy | 0.469854 |
| macro_f1 | 0.438116 |
| majority_accuracy_valid | 0.504008 |
| event trades | 423 |
| event mean net bps | 0.422954 |
| event total net bps | 178.909441 |
| non-overlap trades | 66 |
| non-overlap mean net bps | 0.542674 |
| non-overlap total net bps | 35.816451 |

`runs/research_v3_advanced_h10_single/` trains the larger 364-feature version. It produced positive event PnL, but weaker non-overlap PnL than the base H10 model.

## Walk-forward results

All walk-forward runs use chronological folds with an embargo measured from the prediction horizon. The strict non-overlap metrics keep at most one trade per horizon window.

| Run | Horizon | Features | Balanced accuracy mean | Macro F1 mean | Best strict edge | Strict trades | Strict hit rate | Strict mean net bps | Strict total net bps |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `research_walk_forward_fast_h1` | 1s | 199 | 0.542122 | 0.377255 | 0.7 | 109 | 0.201835 | -0.943474 | -102.838695 |
| `research_walk_forward_fast_h5` | 5s | 199 | 0.476095 | 0.412833 | 0.7 | 23 | 0.521739 | 0.602614 | 13.860131 |
| `research_walk_forward_fast_h10` | 10s | 199 | 0.442962 | 0.417548 | 0.7 | 14 | 0.428571 | 1.332626 | 18.656758 |
| `research_v3_walk_forward_h10_base_2fold` | 10s | 264 | 0.437274 | 0.408211 | 0.5 | 68 | 0.485294 | 0.424646 | 28.875937 |

The 1-second horizon has the highest balanced accuracy, while cost-adjusted strict PnL is negative. The 5-second and 10-second horizons show weaker classification accuracy and better selective edge-threshold behavior. This supports treating probability edge selection as a separate optimization problem from raw direction accuracy.

## Rule baseline

`runs/research_v3_rule_baselines_h10/` tests deterministic signed-feature rules. The strongest rule is `imbalance_l3` with signal threshold 0.7.

| Metric | Value |
|---|---:|
| balanced_accuracy | 0.462582 |
| macro_f1 | 0.306315 |
| event trades | 679 |
| event mean net bps | 0.089612 |
| event total net bps | 60.846659 |
| strict trades | 66 |
| strict hit rate | 0.454545 |
| strict mean net bps | 0.649592 |
| strict total net bps | 42.873102 |

The deterministic imbalance rule remains a strong baseline. Learned models should beat this baseline across multiple days before any trading relevance claim is credible.

## Feature-family ablation

`runs/research_v3_ablation_h10/` completed 4 of 5 planned variants. The local container killed `04_no_lags`; its partial directory is retained for reproducibility.

| Rank | Variant | Feature count | Balanced accuracy | Macro F1 | Event mean net bps | Strict mean net bps | Strict total net bps |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `01_base_lob` | 264 | 0.469854 | 0.438116 | 0.422954 | 0.542674 | 35.816451 |
| 2 | `02_plus_ofi` | 346 | 0.469574 | 0.435941 | 0.482239 | 0.353851 | 27.246516 |
| 3 | `03_plus_shape` | 282 | 0.460050 | 0.422919 | 0.518288 | 0.603698 | 43.466226 |
| 4 | `05_all_features` | 364 | 0.460060 | 0.421608 | 0.355718 | 0.223653 | 18.115893 |

Base LOB features are still competitive. Shape features improved strict mean net bps in the single split, while adding all feature families reduced stability in this sample.

## Main research conclusion

The real L2 sample contains short-horizon directional signal in microprice, imbalance, depth concentration, and related rolling features. The signal is weak and highly cost-sensitive. Single chronological splits can show positive cost-adjusted PnL, and the 10-second walk-forward base run retained positive strict non-overlap PnL. The result remains a research finding on one instrument and one historical date.

## Verification status

The final package was checked with:

```bash
PYTHONPATH=src python -m py_compile src/lob_microprice_lab/*.py
PYTHONPATH=src pytest -q tests/test_features.py tests/test_labels.py tests/test_real_data.py tests/test_research_tools.py
PYTHONPATH=src pytest -q tests/test_pipeline.py
PYTHONPATH=src pytest -q tests/test_diagnostics.py
```

The split test runs passed 8 tests total. Running all tests in one command previously congested the shared container during long research jobs, so Codex should rerun `PYTHONPATH=src pytest -q` locally after dependency installation.

## Recommended next research tasks

1. Add Tardis trade-print conversion and align aggressor trades with reconstructed book snapshots.
2. Run the same experiments across multiple days, symbols, and volatility regimes.
3. Add latency-shifted entry prices, queue-position assumptions, and book-depth slippage simulation.
4. Add blocked bootstrap confidence intervals for strict PnL, hit rate, and trade count.
5. Calibrate probabilities per fold and compare edge thresholds selected by validation PnL versus log-loss/ECE.
6. Add block-shuffle, sign-flip, and per-fold label-permutation null tests.
7. Move from snapshot features to event-stream sequence models only after the tabular baselines are stable.
