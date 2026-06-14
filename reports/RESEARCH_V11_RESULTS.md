# Research V11 Results

V11 continues the 30s+ long-window branch after V10.  The main goal was to test whether long-window templates can be selected online from earlier validation periods rather than by validation-oracle or hindsight template ranking.

## Main conclusion

Stable profit is still not established.

V11 found one encouraging but still insufficient lead: a source-ranked 90s template from the 5-fold H90 ensemble produced positive aggregate PnL under taker bid/ask execution, 0.5s latency, and 1.5 bps cost.  The template is simple:

```json
{
  "edge_threshold": 0.1,
  "direction_mode": "normal",
  "signed_col": null,
  "signed_mode": "none",
  "signed_abs_threshold": 0.0,
  "spread_max_bps": null,
  "vol_col": null,
  "vol_mode": "none",
  "vol_min": null,
  "vol_max": null
}
```

That means it trades the model's probability edge directly when `prob_up - prob_down >= 0.1` or `<= -0.1`, without extra LOB filters.

However, the lead fails the new V11 strict gate because one validation period loses money, the family-wise null audit is weak, and a 180-second micro-period stress turns negative.  This is a research lead, not a deployable strategy.

## New code

- `src/lob_microprice_lab/sequential_selection.py`
  - `sequential-template-audit` CLI
  - online/prequential template selection
  - fixed source-rank selection
  - past-total / past-mean / past-rank-score / past-lower-bound selectors
  - period-level diagnostics
  - period oracle comparator
  - source-rank comparator
  - fixed-signal cost/latency stress
  - shifted-signal null
  - stricter period-min gate
- `tests/test_sequential_selection_v11.py`
- Makefile targets:
  - `sequential-h90-v11-source`
  - `sequential-h90-v11-lower`
  - `sequential-h90-v11-microperiod`
  - `family-null-h90-v11-5fold`

## V11 summary table

The full machine-readable table is in `runs/research_v11_summary.csv`.

| Run | Horizon | Selection | Periods | Trades | Hit rate | Mean net PnL | Total net PnL | Worst period mean | Bootstrap p05 | Null p(total) | Stress gate | Strict gate |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| `research_v11_seq_h45_3fold_source` | 45s | source-rank | 3 | 38 | 39.47% | -2.7793 | -105.6139 | -7.0032 | -5.3728 | 0.6500 | failed | failed |
| `research_v11_seq_h60_3fold_source` | 60s | source-rank | 3 | 24 | 41.67% | -4.8861 | -117.2660 | -10.6478 | -7.1993 | 0.7500 | failed | failed |
| `research_v11_seq_h90_3fold_source` | 90s | source-rank | 3 | 17 | 35.29% | -1.3964 | -23.7395 | -3.6002 | -3.5928 | 0.4250 | failed | failed |
| `research_v11_seq_h90_5fold_source` | 90s | source-rank | 5 | 25 | 44.00% | +4.3192 | +107.9812 | -1.9807 | +0.1744 | 0.0000 | passed | failed |
| `research_v11_family_null_h90_5fold` | 90s | family-wise null on source-rank-1 | 5 folds | 25 | 44.00% | +4.3192 | +107.9812 | -1.9807 | -8.0039 | 0.4667 | passed | failed |
| `research_v11_seq_h90_5fold_lower` | 90s | past lower-bound | 5 | 8 | 50.00% | -0.2027 | -1.6215 | -26.1914 | -18.1146 | 0.3000 | failed | failed |
| `research_v11_seq_h90_5fold_source_p180` | 90s | source-rank, 180s micro-periods | 15 | 15 | 33.33% | -0.8713 | -13.0695 | -24.5067 | -4.4194 | 0.3333 | failed | failed |
| `research_v11_seq_h120_3fold_source` | 120s | source-rank | 3 | 10 | 20.00% | -5.3068 | -53.0676 | -8.2552 | -6.9765 | 0.7250 | failed | failed |

## What improved versus V10

V10 showed that validation-ranked oracle templates fail after family-wise shifted-signal correction.  V11 adds an online selection layer and confirms the same issue from another angle:

1. The 90s 5-fold source-rank template is positive in aggregate and survives simple shifted-signal null and cost/latency stress.
2. The same 90s template has a losing validation period, so the stricter period-min gate rejects it.
3. The family-wise null audit for the same 90s 5-fold family has `p_family_null_max_total_ge_source_rank1 = 0.4667` and `p_family_null_max_mean_ge_source_rank1 = 0.75`, so the observed result is not exceptional after accounting for template-family search.
4. When validation is split into conservative 180-second micro-periods, the same source-ranked 90s rule turns negative.
5. A past-lower-bound online selector also turns negative, which means short-term historical template performance is not yet reliable enough for adaptive template switching.

## Best remaining lead

The best remaining research lead is still H90, specifically the simple source-ranked probability-edge rule from the 5-fold stationary ensemble:

```text
horizon: 90s
selection: first-fold calibration source-rank-1
signal: normal model probability edge, threshold 0.1
execution: taker bid/ask, non-overlap
cost: 1.5 bps
latency: 0.5s
trades: 25
mean net PnL: +4.3192 bps/trade
total net PnL: +107.9812 bps
```

It fails promotion because:

```text
worst period mean PnL: -1.9807 bps
fold bootstrap p05: -8.0039 bps
family-wise null p(total): 0.4667
family-wise null p(mean): 0.75
micro-period stress mean PnL: -0.8713 bps
```

## Current research status

```text
source-ranked 45s/60s/90s/120s on 3-fold runs: failed
source-ranked 90s on 5-fold run: positive aggregate, failed strict period gate
family-wise null on 90s 5-fold source-rank lead: failed
past-lower-bound online selector: failed
180s micro-period stress: failed
stable profit: not established
```

## Next research path

The most useful next step remains real data expansion.  Single-day evidence is now constrained by small samples and fold sensitivity.

Promotion criteria for the next stage should be:

1. At least 20 independent trading sessions or days.
2. At least 100 non-overlap trades after cost and latency.
3. Source-ranked or prequential-selected template only; no validation-ranked oracle.
4. Positive mean PnL in every validation day or acceptable day-level drawdown rule defined before testing.
5. Positive block-bootstrap p05.
6. Family-wise null p-values at or below 0.05.
7. Positive under 3 bps and 5 bps stress where the target venue fee tier requires it.

V11's concrete engineering value is the `sequential-template-audit` tool, because it can be directly reused once multi-day L2 + trade-print data is available.
