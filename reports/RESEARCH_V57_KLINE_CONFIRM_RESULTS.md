# Research V57 Kline Confirmation Results

## Purpose

V57 reruns the fixed V55 sparse BTCUSDC rule on Binance public 1m kline bars instead of aggTrade-derived 1m bars.

Frozen rule: lookback 1440m, horizon reserve 1440m, reversal direction, abs_return_bps q0.995 per fold calibration window, next-open entry, TP80, no stop loss.

## Result

- Gate passed: `True`
- Trades: `11`
- Win rate: `1.000000`
- Total net pnl: `786.500000` bps
- Mean net pnl: `71.500000` bps
- Min trade net pnl: `71.500000` bps
- 8x account return: `62.920000%`
- Failed checks: ``

## V55 Entry Comparison

- V55 comparison available: `True`
- Matched entries: `11`
- Kline-only entries: `0`
- V55-only entries: `0`
- Max entry price absolute diff: `0.0`
- Max threshold absolute diff: `0.18396535374324685`

## Files

- Entries: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v57_btcusdc_sparse_tp_kline_confirm/v57_kline_next_open_entries.csv`
- TP ledger: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v57_btcusdc_sparse_tp_kline_confirm/v57_kline_next_open_tp80_ledger.csv`
- Contract source ledger: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v57_btcusdc_sparse_tp_kline_confirm/v57_kline_next_open_tp80_source_ledger_for_contract_gate.csv`
- Gate directory: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v57_btcusdc_sparse_tp_kline_confirm_contract_gate`
- Summary JSON: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v57_btcusdc_sparse_tp_kline_confirm/v57_summary.json`

## Caveat

This confirms the fixed sparse rule on a second public 1m OHLC source. It does not remove the small sample-size risk: the result still has only 11 trades.
