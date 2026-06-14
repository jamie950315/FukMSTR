# Handoff for Codex - V25 BTC Portfolio Risk Lock

This repository continues the BTC contract research chain through V25.

## Latest promoted bundled-sample policy

```text
version: V25 BTC portfolio risk lock
source trade rule: V24 BTC adaptive exit safety lock
prediction window: 90 seconds
entries: unchanged from V24
exits: unchanged from V24
fee: taker 0.0400% per side, maker 0.0000%
research route: taker entry + taker exit = 8 bps round trip
selected trades: 11
selected-trade win rate on bundled sample: 100.00%
```

## V25 account-level wrapper

```text
normal leverage: 8.0x
emergency leverage: 6.75x
emergency trigger: realized trade <= -20 bps notional
emergency duration: next 10 trades
promoted synthetic stress: four artificial -40 bps notional failures
shock buffer requirement: 1000 bps before estimated liquidation zone
```

V25 changes only exposure. It does not create new trades and does not change the price-direction model.

## Main command

```bash
make btc-portfolio-risk-lock-v25
```

## Main outputs

```text
runs/research_v25_btc_portfolio_risk_lock/summary_v25.json
runs/research_v25_btc_portfolio_risk_lock/REPORT_V25.md
reports/RESEARCH_V25_RESULTS.md
docs/RESEARCH_V25_COMMANDS.md
```

## Current bundled-sample result

```text
V25 gate: passed
selected trades: 11
selected-trade win rate: 100.00%
notional total net PnL: +190.0977 bps
notional mean net PnL: +17.2816 bps/trade
no-compounding account return at 8x: +15.2078%
liquidation buffer approximation before safety shock: +1192.0 bps
entry/exit family add-one p(total): 0.000999
entry/exit family add-one p(mean): 0.000999
```

## Stress results

```text
four synthetic -40 bps failures: +1.5316% minimum account return
four synthetic -40 bps failures: -9.9739% worst drawdown
10 bps taker fee per side + 5 sec delay: +3.5724% account return
50% missed-trade p05: +2.0630% account return
extra +16 bps per trade: +1.1278% account return
```

Five synthetic -40 bps failures are not promoted. Independent multi-day BTCUSDT contract validation is still required before any live-profit claim.

## Tests

```bash
make test-btc-v25-portfolio
make test-split
```

## Next proof step

Freeze V25 exactly as-is and run it on independent BTCUSDT contract days. Do not retune entries, exits, 8x leverage, 6.75x emergency leverage, or the four-loss gate on validation data.

## V26 BTCUSDC contract lock handoff

Latest command:

```bash
make btcusdc-contract-lock-v26
```

Latest report:

```bash
cat reports/RESEARCH_V26_RESULTS.md
cat docs/RESEARCH_V26_COMMANDS.md
cat runs/research_v26_btcusdc_contract_lock/REPORT.md
```

V26 is a BTCUSDC continuation. It keeps the V24/V25 BTC rule frozen and runs a BTCUSDC transfer proxy with 4 bps taker fee per side, 0 bps maker fee, 0.5 bps quote-market surcharge, and 8x / 6.5x emergency leverage. It passes the proxy gate but `true_btcusdc_data_run_completed=false`. The next real work is to download BTCUSDC Binance public files, build a real BTCUSDC ledger, and rerun with `btcusdc_ledger=`.

## V26 BTCUSDC contract lock handoff

Latest V26 command:

```bash
make btcusdc-contract-lock-v26
```

Read:

```bash
cat reports/RESEARCH_V26_RESULTS.md
cat docs/RESEARCH_V26_COMMANDS.md
cat runs/research_v26_btcusdc_contract_lock/REPORT_V26.md
```

V26 does not claim a true BTCUSDC L2 replay. The bundled project has no real BTCUSDC order-book history. It performs a BTCUSDC transfer/stress run from the frozen BTC V24/V25 trade ledger, subtracts a 0.50 bps BTCUSDC quote-market surcharge, and writes a BTCUSDC Binance USD-M public-data manifest.

Main output:

```text
runs/research_v26_btcusdc_contract_lock/
```

Key result:

```text
gate_passed: true
data_mode: transfer_proxy_from_frozen_btc_ledger
true_btcusdc_data_run_completed: false
trades: 11
win_rate: 100.00%
notional_total_net_pnl: +184.5977 bps
8x account_return_no_compounding: +14.7678%
```

True next step: download BTCUSDC files from `runs/research_v26_btcusdc_contract_lock/btcusdc_data_plan/download_commands.sh`, build a BTCUSDC event ledger, then rerun `run_btcusdc_contract_lock(..., btcusdc_ledger=<path>)` without changing thresholds.
