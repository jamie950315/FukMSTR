# Research V08 Results

V08 continued the long-window branch after V07.  The focus was 45s, 60s, 90s, and 120s horizons.  The main goal was to separate a genuinely reusable trading template from a fold-local or validation-selected artifact.

## Main conclusion

Stable profit is still not established.

The most important new result is negative: when the selective template is chosen by source calibration only (`selection_policy=source_rank`), every tested long-window template loses money out-of-fold.  When the template is selected after looking across validation folds (`selection_policy=validation_rank`), several templates look profitable, especially 90s and 120s, but that selection policy is a diagnostic oracle and is not a deployable rule.

This means V08 found useful structure for future hypothesis generation, but the strict no-lookahead promotion gate still fails.

## Main code changes

- Added `src/lob_microprice_lab/fixed_template.py`.
  - Freezes concrete selective candidates before validation.
  - Supports two explicit selection policies:
    - `source_rank`: selects the highest-ranked candidate from source calibration only. This is the strict setting.
    - `validation_rank`: selects the candidate with best validation behavior among pre-frozen templates. This is an oracle-style diagnostic and is data-snooped.
  - Produces candidate leaderboard, selected candidate JSON, selected OOF backtest, stress sweep, shifted-signal null, and promotion gate.
- Added `src/lob_microprice_lab/trade_audit.py`.
  - Adds trade concentration, side/fold breakdown, drawdown, streaks, and MFE/MAE-style path diagnostics.
- Added `src/lob_microprice_lab/portfolio.py`.
  - Combines fixed-template trade ledgers with portfolio-level non-overlap.
  - Useful as a diagnostic for multi-horizon template interactions.
- Added CLI commands:
  - `fixed-template-audit`
  - `audit-trades`
  - `combine-fixed-backtests`
- Added tests:
  - `tests/test_fixed_template_v08.py`
  - `tests/test_trade_audit_v08.py`
  - `tests/test_portfolio_v08.py`

## Strict fixed-template results: source-rank policy

These are the most important V08 numbers.  The template is selected by the first source calibration ranking, then applied to validation folds.

| Horizon | OOF trades | Hit rate | Mean net PnL | Total net PnL | Fold min mean | Gate |
|---:|---:|---:|---:|---:|---:|---|
| 45s | 3 | 33.33% | -6.2682 bps | -18.8047 bps | -9.4439 bps | failed |
| 60s | 24 | 41.67% | -4.8861 bps | -117.2660 bps | -10.6478 bps | failed |
| 90s | 17 | 35.29% | -1.3964 bps | -23.7395 bps | -3.6002 bps | failed |
| 120s | 10 | 20.00% | -5.3068 bps | -53.0676 bps | -8.2552 bps | failed |

Strict source-rank result: the calibration-best templates do not transfer.

## Diagnostic oracle results: validation-rank policy

These are useful for identifying candidate patterns, but they are selected after validation behavior is known.  Treat them as hypothesis generation only.

| Horizon | OOF trades | Hit rate | Mean net PnL | Total net PnL | Stress gate | Gate |
|---:|---:|---:|---:|---:|---|---|
| 45s | 35 | 60.00% | +1.4036 bps | +49.1270 bps | failed | failed |
| 60s | 24 | 62.50% | +2.2668 bps | +54.4025 bps | failed | failed |
| 90s | 17 | 88.24% | +8.1234 bps | +138.0973 bps | passed | failed |
| 120s | 12 | 75.00% | +5.2419 bps | +62.9024 bps | passed | failed |

90s is the strongest diagnostic lead.  It passes the cost/latency stress grid, including 5 bps cost and 2s latency, but it has only 17 trades and a negative fold-level bootstrap p05.  The promotion gate fails on sample size and statistical lower bound.

## Selected diagnostic templates

| Horizon | Diagnostic selected rule |
|---:|---|
| 45s | normal model edge, require agreement with `microprice_dev_bps_l3`, edge 0.1 |
| 60s | inverted model edge, require disagreement with `imbalance_l3`, edge 0.3 |
| 90s | inverted model edge, require disagreement with `microprice_dev_bps_l3`, edge 0.1 |
| 120s | inverted model edge, require agreement with `imbalance_l3`, edge 0.2 |

The repeated appearance of inverted probability edge in 60s+ windows suggests the learned classifier may be systematically miscalibrated or learning a mean-reversion-like reversal regime.  V08 does not promote that idea to a strategy because strict source-ranked selection loses money.

## Portfolio diagnostic

The multi-horizon portfolio diagnostic combines already-priced fixed-template trade ledgers and enforces one open position at a time across horizons.

| Portfolio | Selection policy | Trades | Hit rate | Mean net PnL | Total net PnL | Fold min total | Interpretation |
|---|---|---:|---:|---:|---:|---:|---|
| long-priority | source-rank | 18 | 22.22% | -6.1702 bps | -111.0641 bps | -56.4422 bps | fails |
| long-priority | validation-rank | 26 | 73.08% | +4.8827 bps | +126.9507 bps | +19.0191 bps | oracle diagnostic only |

The validation-ranked portfolio looks strong, but it is constructed from validation-selected templates.  The source-ranked portfolio loses money.  This sharply separates research signal from deployable evidence.

## Trade audit highlights for validation-ranked diagnostic templates

| Horizon | Trades | Mean net PnL | Hit rate | Profit factor | Max drawdown | Top-1 gain share |
|---:|---:|---:|---:|---:|---:|---:|
| 45s | 35 | +1.4036 bps | 60.00% | 1.4710 | -36.6312 bps | 28.06% |
| 60s | 24 | +2.2668 bps | 62.50% | 1.7289 | -25.9479 bps | 16.11% |
| 90s | 17 | +8.1234 bps | 88.24% | 8.0215 | -19.6677 bps | 33.38% |
| 120s | 12 | +5.2419 bps | 75.00% | 2.8594 | -21.2412 bps | 23.84% |

The 90s diagnostic result has high per-trade PnL, but one large winning trade contributes about one third of gains and there are only 17 trades.  This is too sparse for a stable-profit claim.

## Current status

```text
strict source-ranked long-window templates: failed
validation-ranked oracle diagnostics: positive leads found
multi-horizon strict source-ranked portfolio: failed
multi-horizon validation-ranked portfolio: positive diagnostic only
stable profit: not established
```

## Next research path

1. Add true nested template selection: use an early segment to choose one template, freeze it, then test on later dates only.
2. Acquire multi-day L2 + trades data and repeat V08 source-rank audits across at least 20 independent sessions.
3. Add probability recalibration diagnostics; the repeated 60s+ inverted-edge result suggests classifier direction calibration needs direct testing.
4. Treat validation-rank templates as hypothesis seeds, not as strategy outputs.
5. Promote only candidates that pass source-ranked selection, fold bootstrap p05, shifted-signal null, and 3-5 bps stress across multiple days.
