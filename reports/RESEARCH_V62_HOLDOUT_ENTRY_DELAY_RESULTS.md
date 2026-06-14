# Research V62 Holdout Entry Delay Results

## Purpose

V62 stress-tests the V60 design-selected sparse BTCUSDC rule on holdout folds only, varying entry delay without changing thresholds.

Rule under audit: reversal, 1080m lookback, abs_return_bps q0.99, TP80, no stop loss, horizon reserve 1440m.

## Summary

|   entry_delay_min | gate_passed   |   trades |   win_rate |   total_bps |   mean_bps |   min_trade_bps |   account_return_pct |   missed_trade_p05_account_return_pct |   extra_cost_account_return_pct |   promoted_loss_min_account_return_pct | failed_checks                                       |
|------------------:|:--------------|---------:|-----------:|------------:|-----------:|----------------:|---------------------:|--------------------------------------:|--------------------------------:|---------------------------------------:|:----------------------------------------------------|
|                 1 | True          |       12 |   1        |     858     |    71.5    |          71.5   |               68.64  |                             17.16     |                          53.28  |                                44.77   |                                                     |
|                 2 | True          |       12 |   1        |     858     |    71.5    |          71.5   |               68.64  |                             17.16     |                          53.28  |                                44.77   |                                                     |
|                 5 | False         |       12 |   0.916667 |     577.613 |    48.1344 |        -208.887 |               46.209 |                              0.449014 |                          30.849 |                                26.5448 | missed_trade_account_return;synthetic_loss_drawdown |
|                10 | True          |       12 |   1        |     858     |    71.5    |          71.5   |               68.64  |                             17.16     |                          53.28  |                                44.77   |                                                     |
|                15 | True          |       12 |   1        |     858     |    71.5    |          71.5   |               68.64  |                             17.16     |                          53.28  |                                44.77   |                                                     |
|                30 | True          |       12 |   1        |     858     |    71.5    |          71.5   |               68.64  |                             17.16     |                          53.28  |                                44.77   |                                                     |
|                60 | True          |       12 |   1        |     858     |    71.5    |          71.5   |               68.64  |                             17.16     |                          53.28  |                                44.77   |                                                     |

## Files

- Summary CSV: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v62_btcusdc_sparse_tp_holdout_entry_delay/v62_holdout_entry_delay_gate_summary.csv`
- Summary JSON: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v62_btcusdc_sparse_tp_holdout_entry_delay/v62_summary.json`

## Caveat

This is holdout-only relative to the V60 selector split, but it is still historical BTCUSDC data. It does not replace future unseen validation.
