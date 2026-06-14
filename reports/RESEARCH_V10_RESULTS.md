# Research V10 Results

V10 continues the 30s+ long-window branch after V09.  The main goal was to test whether the attractive 45s/60s/90s/120s validation-ranked leads survive correction for template-search bias.

## Main conclusion

Stable profit is still not established.

The key V10 result is negative but useful: once the full searched template family is compared against a family-wise shifted-signal null, the long-window oracle-looking results no longer pass.  The best H90 template still looks strong on the single-day validation set, but a shifted-signal null that is allowed to search across the same 80-template family can often manufacture results of similar size.

This means the current positive long-window results are better interpreted as template-search artifacts or weak hypotheses, not as evidence of a deployable edge.

## New code

- `src/lob_microprice_lab/selection_bias.py`
  - `template-family-null-audit` CLI
  - family-wise shifted-signal null test
  - source-rank-1 vs validation-oracle comparison
  - fold-to-fold template-rank correlation
  - optimistic required-trade-count estimate for positive one-sided CI
- `tests/test_selection_bias_v10.py`
- Makefile targets:
  - `family-null-h90-v10`
  - `family-null-h120-v10`

## V10 family-wise audit summary

All runs use taker bid/ask execution, 0.5s latency, 1.5 bps cost, first-fold template pool, top 80 templates, and 80 shifted-signal null runs.

| Horizon | Oracle trades | Oracle hit rate | Oracle mean net PnL | Oracle total net PnL | Source-rank-1 mean | Source-rank-1 total | Family p(total) | Family p(mean) | Family null total p95 | Fold-rank corr mean | Gate |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 45s | 35 | 60.00% | +1.4036 bps | +49.1270 bps | -2.7793 bps | -105.6139 bps | 0.6875 | 0.9875 | 117.7506 bps | -0.0642 | failed |
| 60s | 24 | 62.50% | +2.2668 bps | +54.4025 bps | -4.8861 bps | -117.2660 bps | 0.7375 | 1.0000 | 131.8902 bps | +0.1724 | failed |
| 90s | 17 | 88.24% | +8.1234 bps | +138.0973 bps | -1.3964 bps | -23.7395 bps | 0.1000 | 0.4375 | 156.1539 bps | -0.0838 | failed |
| 120s | 12 | 75.00% | +5.2419 bps | +62.9024 bps | -5.3068 bps | -53.0676 bps | 0.7250 | 0.9125 | 123.5138 bps | +0.0803 | failed |

Interpretation of the p-values:

- `Family p(total)` asks how often a null run can find some shifted template with total PnL at least as high as the actual selected oracle template.
- `Family p(mean)` asks the same for mean PnL per trade.
- A robust candidate should be near or below 0.05 on both, while also having enough trades and positive fold-level bootstrap lower bounds.

H90 is the strongest remaining diagnostic lead by total PnL.  It reaches +138.10 bps total, but the family-wise total p-value is 0.10 and the family-wise mean p-value is 0.4375.  The null family p95 total is +156.15 bps, above the actual H90 result.  This is strong evidence that the observed H90 result is not exceptional after accounting for template search.

## Source-rank-1 check

The source-rank-1 template is the best template selected from the first calibration fold before validation.  This is closer to a deployable rule than the validation oracle.  It loses money at every tested long horizon:

| Horizon | Source-rank-1 mean net PnL | Source-rank-1 total net PnL |
|---:|---:|---:|
| 45s | -2.7793 bps | -105.6139 bps |
| 60s | -4.8861 bps | -117.2660 bps |
| 90s | -1.3964 bps | -23.7395 bps |
| 120s | -5.3068 bps | -53.0676 bps |

This is the most important practical result of V10: the rule chosen from past data fails to transfer, while the rule chosen after looking at validation can look profitable.

## Fold-rank stability

Template profitability rankings are unstable across folds:

| Horizon | Mean Spearman rank correlation |
|---:|---:|
| 45s | -0.0642 |
| 60s | +0.1724 |
| 90s | -0.0838 |
| 120s | +0.0803 |

A stable strategy family should show positive fold-to-fold ranking persistence.  Current rank correlations are near zero or negative, so the single-day folds do not support template transfer.

## Key files

```text
src/lob_microprice_lab/selection_bias.py
tests/test_selection_bias_v10.py
runs/research_v10_family_null_h45_top80/
runs/research_v10_family_null_h60_top80/
runs/research_v10_family_null_h90_top80/
runs/research_v10_family_null_h120_top80/
runs/research_v10_summary.csv
```

Each audit directory contains:

```text
REPORT.md
summary.json
candidate_family_actual.csv
familywise_shift_null.csv
fold_rank_correlation.csv
selected_oracle_oof_backtest.csv
source_rank1_oof_backtest.csv
selected_oracle_stress.csv
source_rank1_stress.csv
```

## Current research status

```text
v08 validation-ranked oracle leads: positive diagnostic only
v09 prequential H90 template transfer: positive but too sparse and fold-sensitive
v10 family-wise null correction: failed
source-ranked deployable templates: failed
stable profit: not established
```

## Next research path

Single-day template experiments are now near their evidence limit.  The next high-value step is data expansion rather than more template search on this sample:

1. Add multi-day Tardis L2 and trade-print ingestion.
2. Require at least 20 independent sessions and 100+ non-overlap trades before promotion.
3. Run the V10 family-wise null audit per session and on pooled sessions.
4. Promote only templates selected by past sessions, then tested on future sessions.
5. Keep family-wise p-values, fold bootstrap p05, and source-ranked PnL as hard gates.
