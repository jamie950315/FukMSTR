# V13 Commands: Continue From Uploaded V12 With Multi-timeframe K-line Data

V13 starts from the uploaded v12 project state. The original v12 H90 slot-preserving OFI veto result is preserved and used as the baseline.

## Verify the uploaded v12 baseline

```bash
make test-split

PYTHONPATH=src python -m lob_microprice_lab.cli slot-veto-audit \
  --ensemble-dir runs/research_v09_ensemble_h90_5fold_stationary \
  --out runs/local_v12_slot_veto_h90_ofi_l5_q90 \
  --horizon-sec 90 \
  --cost-bps 1.5 \
  --latency-sec 0.5 \
  --edge-threshold 0.1 \
  --filter-col ofi_sum_l5_norm \
  --filter-operator '<=' \
  --filter-quantile 0.9 \
  --family-filter-cols ofi_sum_l3_norm,ofi_sum_l5_norm,ofi_sum_l10_norm \
  --family-quantiles 0.5,0.6,0.7,0.8,0.9 \
  --stress-cost-bps-values 1.5,3.0,5.0 \
  --stress-latency-sec-values 0,0.5,1.0,2.0 \
  --shift-null-runs 80 \
  --family-shift-runs 80 \
  --gate-min-oof-trades 20 \
  --gate-min-periods-with-trades 5 \
  --gate-min-period-mean-net-bps 0 \
  --gate-max-family-null-p-total 0.05 \
  --gate-max-family-null-p-mean 0.10 \
  --clean
```

Equivalent Make target:

```bash
make slot-veto-h90-v12
```

## Build K-line cache

```bash
make kline-cache-v13
```

This derives `1s,5s,15s,1m,5m,15m` candles from the bundled L2 mid price and writes a leakage audit next to the cache.

## Direct K-line retraining on the v12 H90 fold schedule

```bash
make kline-h90-v13-v12folds
```

This appends 252 K-line features to the LOB feature set and retrains the H90 model using the same 5-fold walk-forward ratios as v12.

Result in the packaged research run:

```text
run: runs/research_v13_kline_h90_5fold_stationary_v12folds
gate: failed
trades: 25
total net PnL: +26.1413 bps
mean net PnL: +1.0457 bps/trade
worst fold mean: -8.9380 bps/trade
bootstrap p05 min: -18.3263 bps/trade
stress min mean: -1.3956 bps/trade
```

Conclusion: direct K-line retraining was positive in aggregate but not stable enough to promote.

## Calibration-only K-line weight search

```bash
make kline-weight-h90-v13
```

This searches calibration-only weights over the base probability edge and per-timeframe K-line signals, then applies the selected weights to validation.

Packaged result:

```text
run: runs/research_v13_kline_weight_h90_v12folds
gate: failed
trades: 20
total net PnL: +24.8869 bps
mean net PnL: +1.2443 bps/trade
worst fold mean: -10.0763 bps/trade
bootstrap p05: -4.8770 bps/trade
stress min mean: -2.4937 bps/trade
```

Conclusion: unrestricted K-line weight search overfit the single-day sample and failed fold/bootstrap/stress gates.

## Fixed K-line probability blend overlay

```bash
make kline-blend-alpha010-v13
```

This blends the original v12 source ensemble with the K-line-retrained ensemble using a fixed 10% K-line model probability contribution:

```text
blended_prob = 0.90 * v12_prob + 0.10 * kline_model_prob
```

The blended directory is a normal ensemble directory, so the existing v12 `slot-veto-audit` can consume it unchanged.

## Main V13 gate check: fixed K-line blend plus v12 OFI slot-veto

```bash
make slot-veto-kline-blend-v13
```

Packaged result:

```text
run: runs/research_v13_slot_veto_kline_blend_alpha010_h90
gate: passed
trades: 23
hit rate: 52.17%
mean net PnL: +6.5838 bps/trade
total net PnL: +151.4272 bps
worst fold mean: +2.2604 bps/trade
bootstrap mean p05: +2.4937 bps/trade
stress min mean: +2.8068 bps/trade
stress min total: +64.5565 bps
shift-null p(total): 0.0000
shift-null p(mean): 0.0000
OFI-family null p(total): 0.0000
OFI-family null p(mean): 0.0375
```

Important caveat: the V13 gate uses the existing v12 OFI-family correction. It does not yet include a full alpha-family correction for selecting the K-line blend ratio. Treat this as a single-day research pass, not as established stable profit.

## Useful summary files

```text
runs/research_v13_summary.csv
runs/research_v13_alpha_blend_scan.csv
reports/RESEARCH_V13_RESULTS.md
docs/KLINE_DATA_SCHEMA.md
```
