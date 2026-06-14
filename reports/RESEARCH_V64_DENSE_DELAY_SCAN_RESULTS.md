# Research V64 Dense Delay Scan Results

## Purpose

V64 scans every entry delay from 0 to 120 minutes for the V60 design-selected sparse BTCUSDC rule on holdout folds only.

The rule and performance thresholds are unchanged. The dense scan evaluates the same V26 contract checks in-memory and marks the data-manifest check as already satisfied by the existing BTCUSDC manifest instead of writing 121 duplicate manifests.

## Summary

- Delay range: `0..120` minutes
- Delays tested: `121`
- Passing delays: `111`
- Failing delays: `10`
- Pass rate: `0.917355`
- Worst delay by account return: `119`
- Worst account return: `6.079006%`

## Pass/Fail Ranges

| value   |   start |   end |   count |
|:--------|--------:|------:|--------:|
| True    |       0 |     4 |       5 |
| False   |       5 |     5 |       1 |
| True    |       6 |   108 |     103 |
| False   |     109 |   110 |       2 |
| True    |     111 |   111 |       1 |
| False   |     112 |   113 |       2 |
| True    |     114 |   115 |       2 |
| False   |     116 |   120 |       5 |

## Worst 10 Delays

|   entry_delay_min |   entry_count |   tp_loss_count_after_surcharge |   tp_take_profit_rate | gate_passed   | failed_checks                                                                                                                                                  |   trades |   win_rate |   total_bps |   mean_bps |   min_trade_bps |   max_drawdown_bps |   account_return_pct |   account_max_drawdown_pct |   missed_trade_p05_account_return_pct |   extra_cost_account_return_pct |   promoted_loss_min_account_return_pct |   promoted_loss_worst_drawdown_pct |   fold_min_total_net_pnl_bps |   blocks5_min_total_net_pnl_bps |   blocks10_min_total_net_pnl_bps |
|------------------:|--------------:|--------------------------------:|----------------------:|:--------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------|---------:|-----------:|------------:|-----------:|----------------:|-------------------:|---------------------:|---------------------------:|--------------------------------------:|--------------------------------:|---------------------------------------:|-----------------------------------:|-----------------------------:|--------------------------------:|---------------------------------:|
|               119 |            12 |                               2 |              0.833333 | False         | win_rate;total_net_pnl;mean_net_pnl;no_loss_account_return;missed_trade_account_return;extra_cost_account_return;synthetic_loss_return;synthetic_loss_drawdown |       12 |   0.833333 |     125.437 |    10.4531 |        -379.769 |           -446.563 |              6.07901 |                   -32.1735 |                            -24.285    |                        -5.32504 |                               -4.32099 |                           -42.5735 |                     -138.294 |                       -236.769  |                         -308.269 |
|               120 |            12 |                               2 |              0.833333 | False         | win_rate;total_net_pnl;mean_net_pnl;no_loss_account_return;missed_trade_account_return;extra_cost_account_return;synthetic_loss_return;synthetic_loss_drawdown |       12 |   0.833333 |     124.71  |    10.3925 |        -386.225 |           -447.29  |              6.11765 |                   -32.1348 |                            -24.3432   |                        -5.38323 |                               -4.28235 |                           -42.5348 |                     -132.565 |                       -243.225  |                         -314.725 |
|               118 |            12 |                               2 |              0.833333 | False         | win_rate;total_net_pnl;mean_net_pnl;no_loss_account_return;missed_trade_account_return;extra_cost_account_return;synthetic_loss_return;synthetic_loss_drawdown |       12 |   0.833333 |     140.401 |    11.7001 |        -375.636 |           -431.599 |              7.21416 |                   -31.0383 |                            -23.0879   |                        -4.12788 |                               -3.18584 |                           -41.4383 |                     -127.462 |                       -232.636  |                         -304.136 |
|               117 |            12 |                               2 |              0.833333 | False         | win_rate;total_net_pnl;mean_net_pnl;no_loss_account_return;missed_trade_account_return;extra_cost_account_return;synthetic_loss_return;synthetic_loss_drawdown |       12 |   0.833333 |     161.278 |    13.4398 |        -374.592 |           -410.722 |              8.86863 |                   -29.3839 |                            -21.4178   |                        -2.45775 |                               -1.53137 |                           -39.7839 |                     -107.63  |                       -231.592  |                         -303.092 |
|               116 |            12 |                               2 |              0.833333 | False         | win_rate;total_net_pnl;mean_net_pnl;no_loss_account_return;missed_trade_account_return;extra_cost_account_return;synthetic_loss_return;synthetic_loss_drawdown |       12 |   0.833333 |     163.175 |    13.5979 |        -374.024 |           -408.825 |              9.01183 |                   -29.2407 |                            -21.266    |                        -2.30603 |                               -1.38817 |                           -39.6407 |                     -106.302 |                       -231.024  |                         -302.524 |
|               110 |            12 |                               1 |              0.916667 | False         | missed_trade_account_return;synthetic_loss_drawdown                                                                                                            |       12 |   0.916667 |     369.397 |    30.7831 |        -417.103 |           -417.103 |             22.0443  |                   -33.3682 |                            -16.2082   |                        14.1918  |                               11.6443  |                           -35.9682 |                      143     |                       -274.103  |                         -345.603 |
|               109 |            12 |                               1 |              0.916667 | False         | missed_trade_account_return;synthetic_loss_drawdown                                                                                                            |       12 |   0.916667 |     383.907 |    31.9923 |        -402.593 |           -402.593 |             23.2051  |                   -32.2074 |                            -15.0474   |                        15.3526  |                               12.8051  |                           -34.8074 |                      143     |                       -259.593  |                         -331.093 |
|               112 |            12 |                               1 |              0.916667 | False         | missed_trade_account_return;synthetic_loss_drawdown                                                                                                            |       12 |   0.916667 |     406.747 |    33.8955 |        -379.753 |           -379.753 |             25.0322  |                   -30.3803 |                            -13.2203   |                        17.1797  |                               14.6322  |                           -32.9803 |                      143     |                       -236.753  |                         -308.253 |
|               113 |            12 |                               1 |              0.916667 | False         | missed_trade_account_return;synthetic_loss_drawdown                                                                                                            |       12 |   0.916667 |     409.352 |    34.1127 |        -377.148 |           -377.148 |             25.2407  |                   -30.1718 |                            -13.0118   |                        17.3882  |                               14.8407  |                           -32.7718 |                      143     |                       -234.148  |                         -305.648 |
|                 5 |            12 |                               1 |              0.916667 | False         | missed_trade_account_return;synthetic_loss_drawdown                                                                                                            |       12 |   0.916667 |     577.613 |    48.1344 |        -208.887 |           -208.887 |             46.209   |                   -16.711  |                              0.449014 |                        30.849   |                               26.5448  |                           -18.7777 |                      143     |                        -65.8873 |                         -137.387 |

## V62 Consistency

- Checked delays: `7`
- All matched V62 gate/metrics: `True`

## Files

- Delay scan CSV: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v64_btcusdc_sparse_tp_dense_delay_scan/v64_dense_delay_contract_gate_summary.csv`
- Range CSV: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v64_btcusdc_sparse_tp_dense_delay_scan/v64_dense_delay_pass_fail_ranges.csv`
- Combined TP ledger CSV: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v64_btcusdc_sparse_tp_dense_delay_scan/v64_dense_delay_combined_tp80_ledger.csv`
- Summary JSON: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v64_btcusdc_sparse_tp_dense_delay_scan/v64_summary.json`

## Caveat

This is a historical holdout delay robustness map. It does not replace future unseen BTCUSDC validation.
