# Research V58 Null Audit Results

## Purpose

V58 audits whether the fixed V55/V57 sparse BTCUSDC TP80 result is easily reproduced by simple negative controls.

Frozen rule under audit: lookback 1440m, horizon reserve 1440m, reversal direction, abs_return_bps q0.995 per fold calibration window, next-open entry, TP80, no stop loss.

## Observed Kline Baseline

- Trades: `11`
- Wins: `11`
- Win rate: `1.000000`
- Total net pnl after BTCUSDC surcharge: `786.500000` bps
- Min trade net pnl after BTCUSDC surcharge: `71.500000` bps

## Direction Flip Control

- Gate passed: `False`
- Failed checks: `win_rate;total_net_pnl;mean_net_pnl;no_loss_account_return;missed_trade_account_return;extra_cost_account_return;synthetic_loss_return;synthetic_loss_drawdown`
- Trades: `11`
- Wins: `9`
- Win rate: `0.818182`
- Total net pnl after BTCUSDC surcharge: `-88.188760` bps
- Min trade net pnl after BTCUSDC surcharge: `-367.482141` bps

## Random Time Null

- Runs: `2000`
- Seed: `580058`
- P(null wins >= observed wins): `0.028500`
- P(null total pnl >= observed total pnl): `0.021500`
- P(null wins and total pnl both >= observed): `0.021500`
- Null wins quantiles: `{'p01': 4.0, 'p05': 5.0, 'p50': 8.0, 'p95': 10.0, 'p99': 11.0, 'max': 11.0}`
- Null total pnl quantiles: `{'p01': -1986.2706440557017, 'p05': -1426.1483532668294, 'p50': -172.20014023247276, 'p95': 624.961457078518, 'p99': 786.5, 'max': 786.5}`

## Files

- Observed entries: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v58_btcusdc_sparse_tp_null_audit/v58_observed_kline_entries.csv`
- Direction flip ledger: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v58_btcusdc_sparse_tp_null_audit/v58_direction_flip_tp80_ledger.csv`
- Direction flip gate directory: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v58_btcusdc_direction_flip_contract_gate`
- Random null summary: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v58_btcusdc_sparse_tp_null_audit/v58_random_time_null_summary.csv`
- Summary JSON: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v58_btcusdc_sparse_tp_null_audit/v58_summary.json`

## Caveat

This is a negative-control audit. It strengthens or weakens the current sparse rule evidence, but it does not create more observed trades or prove future performance.
