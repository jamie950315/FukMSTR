# Research V63 Delay-5 Anomaly Audit Results

## Purpose

V63 explains the single V62 holdout entry-delay failure without changing the V60 design-selected rule or thresholds.

Rule under audit: reversal, 1080m lookback, abs_return_bps q0.99, TP80, no stop loss, horizon reserve 1440m.

## Finding

The V62 delay=5 failure is one fold-6 short signal at 2026-03-04 09:19:00+00:00. Delay=5 entered at 71102.3, setting TP80 at 70533.4816; the best low before horizon was 70555.0, missing the target by 3.0508 bps, then exiting at horizon for -208.8873 bps after surcharge. The other tested delays for the same signal reached TP80 because their entry prices produced easier short targets.

## Delay Comparison

|   fold |   signal_idx | signal_timestamp          |   entry_delay_min |     idx | timestamp                 |   signal |   entry_px |   tp_target_px | exit_timestamp            | exit_reason   |   exit_px |   net_pnl_bps |   final_net_pnl_bps | target_hit_in_path   | first_hit_timestamp       |   first_hit_px | best_touch_timestamp      |   best_touch_px |   target_miss_bps |   hold_sec |
|-------:|-------------:|:--------------------------|------------------:|--------:|:--------------------------|---------:|-----------:|---------------:|:--------------------------|:--------------|----------:|--------------:|--------------------:|:---------------------|:--------------------------|---------------:|:--------------------------|----------------:|------------------:|-----------:|
|      6 |      1137408 | 2026-03-04 09:19:00+00:00 |                 1 | 1137409 | 2026-03-04 09:20:00+00:00 |       -1 |    71167.2 |        70597.9 | 2026-03-04 12:29:00+00:00 | take_profit   |   70597.9 |        72     |              71.5   | True                 | 2026-03-04 12:29:00+00:00 |        70587.6 | 2026-03-04 12:31:00+00:00 |           70555 |          -6.07135 |      11340 |
|      6 |      1137408 | 2026-03-04 09:19:00+00:00 |                 2 | 1137410 | 2026-03-04 09:21:00+00:00 |       -1 |    71323.1 |        70752.5 | 2026-03-04 12:17:00+00:00 | take_profit   |   70752.5 |        72     |              71.5   | True                 | 2026-03-04 12:17:00+00:00 |        70748.3 | 2026-03-04 12:31:00+00:00 |           70555 |         -27.9164  |      10560 |
|      6 |      1137408 | 2026-03-04 09:19:00+00:00 |                 5 | 1137413 | 2026-03-04 09:24:00+00:00 |       -1 |    71102.3 |        70533.5 | 2026-03-05 09:24:00+00:00 | horizon       |   72527.1 |      -208.387 |            -208.887 | False                | NaT                       |          nan   | 2026-03-04 12:31:00+00:00 |           70555 |           3.05081 |      86400 |
|      6 |      1137408 | 2026-03-04 09:19:00+00:00 |                10 | 1137418 | 2026-03-04 09:29:00+00:00 |       -1 |    71287.9 |        70717.6 | 2026-03-04 12:18:00+00:00 | take_profit   |   70717.6 |        72     |              71.5   | True                 | 2026-03-04 12:18:00+00:00 |        70686.1 | 2026-03-04 12:31:00+00:00 |           70555 |         -22.9924  |      10140 |
|      6 |      1137408 | 2026-03-04 09:19:00+00:00 |                15 | 1137423 | 2026-03-04 09:34:00+00:00 |       -1 |    71199.3 |        70629.7 | 2026-03-04 12:24:00+00:00 | take_profit   |   70629.7 |        72     |              71.5   | True                 | 2026-03-04 12:24:00+00:00 |        70628.5 | 2026-03-04 12:31:00+00:00 |           70555 |         -10.5771  |      10200 |
|      6 |      1137408 | 2026-03-04 09:19:00+00:00 |                30 | 1137438 | 2026-03-04 09:49:00+00:00 |       -1 |    71790.2 |        71215.9 | 2026-03-04 10:48:00+00:00 | take_profit   |   71215.9 |        72     |              71.5   | True                 | 2026-03-04 10:48:00+00:00 |        71177.3 | 2026-03-04 12:31:00+00:00 |           70555 |         -92.7993  |       3540 |
|      6 |      1137408 | 2026-03-04 09:19:00+00:00 |                60 | 1137468 | 2026-03-04 10:19:00+00:00 |       -1 |    71499.9 |        70927.9 | 2026-03-04 11:36:00+00:00 | take_profit   |   70927.9 |        72     |              71.5   | True                 | 2026-03-04 11:36:00+00:00 |        70892.6 | 2026-03-04 12:31:00+00:00 |           70555 |         -52.5746  |       4620 |

## Files

- Delay comparison CSV: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v63_btcusdc_sparse_tp_delay5_anomaly_audit/v63_delay5_anomaly_delay_comparison.csv`
- Price path CSV: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v63_btcusdc_sparse_tp_delay5_anomaly_audit/v63_delay5_anomaly_price_path.csv`
- Summary JSON: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v63_btcusdc_sparse_tp_delay5_anomaly_audit/v63_summary.json`

## Caveat

This audit explains the historical delay-5 failure point. It does not convert the strategy into future unseen validation.
