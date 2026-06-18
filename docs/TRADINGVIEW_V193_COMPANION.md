# TradingView V193 Companion Strategy

This document explains how to use `tradingview/btcusdc_v193_companion_strategy.pine` in TradingView.

## What It Is

The Pine file is a TradingView companion strategy for the promoted BTCUSDC V193 paper iteration. It provides:

- a Pine v6 `strategy()` that can be pasted into TradingView;
- long and short proxy entries based on EMA, RSI, ATR, and chart breakout conditions;
- ATR stop loss, ATR take profit, and timed exits;
- TradingView alert payloads tagged with `tradingview_v193_companion`;
- a V193-style 6-hour premium throttle for the long-base top5 proxy bucket.

## Important Limitation

This TradingView script cannot exactly reproduce the backend V193 research path.

Backend V193 depends on research-only columns that TradingView Pine cannot see:

- `indicator_key`;
- `leg`;
- `direction_probability`;
- `premium_close_bps_6h` from the research account path;
- `v188_state_action`;
- `v189_state_action`;
- `v190_state_action`;
- `v191_state_action`;
- `v192_state_action`.

The original V193 rule only throttles historical rows where:

```text
indicator_key = v125_top5_lb14_strict
side = long
leg = base
v188_state_action = unchanged
v189_state_action = unchanged
v190_state_action = unchanged
v191_state_action = unchanged
v192_state_action = unchanged
premium_close_bps_6h >= -4.576517
```

The Pine strategy approximates that target bucket with an OHLCV-only `top5LongBaseProxy` and applies the same threshold:

```text
premium_close_bps_6h >= -4.576517
```

Treat TradingView results as a visual and alerting companion, not as proof that the backend V193 backtest has been reproduced.

## How To Use

1. Open TradingView.
2. Open a BTCUSDC chart. A perpetual/futures BTCUSDC chart is preferred if you want the premium throttle to have meaning.
3. Open Pine Editor.
4. Paste `tradingview/btcusdc_v193_companion_strategy.pine`.
5. Save and add it to the chart.
6. In settings, set `Spot/reference symbol for premium` to the spot or reference market used to compute the 6-hour premium. For example, use a BTCUSDC spot symbol when the chart is a BTCUSDC perpetual/futures symbol.
7. Create alerts from the strategy order fills or from the alert conditions:
   - `V193 companion long`;
   - `V193 companion short`;
   - `V193 premium throttle block`.

## Verification Status

Local repository verification covers the script structure, required V193 constants, alert payloads, and non-lookahead `request.security()` usage. Browser smoke verification confirmed that TradingView opens the BTCUSDC chart, opens Pine Editor, and accepts the pasted Pine v6 script text.

Final `Add to chart` compilation requires a signed-in TradingView session. In an unsigned browser session, TradingView shows a sign-in dialog before completing the add-to-chart/compile step. If TradingView returns a Pine compiler error after sign-in, copy the exact error text and line number back into this repository workflow.

## Alert Payloads

Long alert:

```json
{"source":"tradingview_v193_companion","strategy":"BTCUSDC_V193_COMPANION","side":"long","symbol":"{{ticker}}","time":"{{time}}","price":"{{close}}"}
```

Short alert:

```json
{"source":"tradingview_v193_companion","strategy":"BTCUSDC_V193_COMPANION","side":"short","symbol":"{{ticker}}","time":"{{time}}","price":"{{close}}"}
```

Throttle alert:

```json
{"source":"tradingview_v193_companion","strategy":"BTCUSDC_V193_COMPANION","event":"v193_throttle_block","symbol":"{{ticker}}","time":"{{time}}","price":"{{close}}"}
```

## Suggested Starting Settings

- Use a 1-minute or 5-minute chart for short-term monitoring.
- Keep `Enable V193 top5 long-base premium throttle` on when charting a futures/perpetual BTCUSDC market with a valid spot reference symbol.
- Turn the throttle off if the chart and premium reference symbol are the same spot market, because the premium proxy will be close to zero and may block too many long-base proxy entries.
- Keep `Timed exit bars` aligned with the chart interval. For example, `30` bars on a 1-minute chart approximates the backend default 30-minute holding horizon.

## Live Trading Warning

This repository still treats V193 as paper trading and monitoring only. Real-money launch remains blocked unless the readiness and launch preflight gates pass with fresh forward and execution evidence.
