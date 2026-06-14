# V13 K-line Data Schema

V13 adds leakage-safe candlestick / K-line features to the existing v12 limit-order-book workflow.
The feature builder can either derive candles from the bundled L2 book mid price or read external OHLCV candle files.

## Supported timeframes

The parser accepts millisecond, second, minute, hour, and day suffixes:

```text
500ms, 1s, 5s, 15s, 1m, 5m, 15m, 1h, 1d
```

The main V13 research run used:

```text
1s, 5s, 15s, 1m, 5m, 15m
```

## External OHLCV file columns

Each CSV or CSV.GZ should contain at least these columns, using either canonical names or common aliases:

| Canonical | Accepted aliases | Required |
|---|---|---|
| `timestamp` | `timestamp`, `open_time`, `open_ts`, `start_time`, `date`, `datetime` | yes |
| `open` | `open`, `o` | yes |
| `high` | `high`, `h` | yes |
| `low` | `low`, `l` | yes |
| `close` | `close`, `c` | yes |
| `volume` | `volume`, `vol`, `v`, `base_volume` | no, defaults to 0 |
| `close_ts` | `close_ts`, `close_time`, `end_time`, `end_ts` | no, inferred |

Timestamps may be ISO strings or numeric epoch values supported by the project timestamp parser.

## Timestamp semantics and leakage rule

By default, `timestamp` means the bar open time. If `close_ts` is absent, V13 infers:

```text
close_ts = timestamp + timeframe
```

A candle can only affect an event when:

```text
candle.close_ts <= event.timestamp - decision_lag_sec
```

This prevents the model from seeing the close/high/low of a still-open candle. Every K-line cache writes an audit with:

```text
ok
violations
max_overrun_ns
missing_rate_by_timeframe
feature_columns
```

The main V13 run produced `ok: true` and `max_overrun_ns: 0`.

## Feature families

For each timeframe V13 creates K-line columns prefixed as `kline_<tf>_...`, including:

```text
open, high, low, close, volume
range_bps, body_bps, upper_wick_bps, lower_wick_bps, close_pos, direction
volume_log, signal
ret_<lookback>_bps, mom_<lookback>_bps, rv_<lookback>_bps
ma_gap_<lookback>_bps, range_z_<lookback>, volume_z_<lookback>, trend_eff_<lookback>
age_sec
```

The main run used lookbacks:

```text
1, 3, 6, 12
```

## Example: build a K-line cache from L2 book data

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli build-kline-cache \
  --book data/real_tardis/book_depth10_500ms.csv \
  --out runs/local_v13_kline_cache.csv \
  --timeframes 1s,5s,15s,1m,5m,15m \
  --lookbacks 1,3,6,12 \
  --decision-lag-sec 0
```

## Example: use external candle files

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli ensemble-walk-forward \
  --book data/real_tardis/book_depth10_500ms.csv \
  --config runs/research_v09_ensemble_h90_5fold_stationary/config_resolved.yaml \
  --out runs/local_v13_kline_external_h90 \
  --horizon-sec 90 \
  --threshold-bps 1 \
  --models logistic \
  --candidate-edges 0.1,0.2,0.3,0.5,0.7 \
  --cost-bps 1.5 \
  --latency-sec 0.5 \
  --folds 5 \
  --min-train-ratio 0.35 \
  --valid-ratio 0.10 \
  --calibration-ratio 0.2 \
  --top-k-features 80 \
  --stationary-only \
  --kline-timeframes 1s,5s,1m,5m \
  --kline-candle '1s:data/klines/1s/2026-*.csv' \
  --kline-candle '5s:data/klines/5s/2026-*.csv' \
  --kline-candle '1m:data/klines/1m/2026-*.csv' \
  --kline-candle '5m:data/klines/5m/2026-*.csv' \
  --kline-lookbacks 1,3,6,12 \
  --kline-decision-lag-sec 0 \
  --clean
```

Multiple `--kline-candle timeframe:path` specs can be supplied. Glob patterns are expanded, so daily or monthly split files can be passed directly.
