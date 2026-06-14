# Research V60 Design Selector Audit Results

## Purpose

V60 ranks the V59 parameter neighborhood using design folds only, then reports the selected candidate on holdout folds.

This is an audit only. It does not promote or replace the V55/V57 fixed rule.

## Split

- Design folds: `[1, 2, 3, 4]`
- Holdout folds: `[5, 6, 7]`
- Total candidates: `50`

## Design-Selected Candidate

- Direction: `reversal`
- Lookback minutes: `1080`
- Quantile: `0.99`
- Design rank: `1`
- Design trades/wins: `6/6`
- Design total net pnl: `429.000000` bps
- Holdout trades/wins: `12/12`
- Holdout win rate: `1.000000`
- Holdout total net pnl: `858.000000` bps
- Holdout positive screen: `True`

## Fixed V55/V57 Rule

- Design rank: `10`
- Design trades/wins: `4/4`
- Design total net pnl: `286.000000` bps
- Holdout trades/wins: `7/7`
- Holdout win rate: `1.000000`
- Holdout total net pnl: `500.500000` bps
- Holdout positive screen: `True`

## Family Summary

- Design positive screen pass count: `33`
- Holdout positive screen pass count: `24`
- Both design and holdout positive screen pass count: `18`
- Design-selected is fixed V55/V57 rule: `False`

## Top 10 By Design Pnl

| direction   |   lookback_minutes |   quantile |   trades |   wins |   win_rate |   take_profit_rate |   total_net_pnl_bps |   mean_net_pnl_bps |   min_trade_net_pnl_bps |   max_trade_net_pnl_bps |   max_hold_sec |   design_trades |   design_wins |   design_win_rate |   design_take_profit_rate |   design_total_net_pnl_bps |   design_mean_net_pnl_bps |   design_min_trade_net_pnl_bps |   design_max_trade_net_pnl_bps |   design_max_hold_sec |   holdout_trades |   holdout_wins |   holdout_win_rate |   holdout_take_profit_rate |   holdout_total_net_pnl_bps |   holdout_mean_net_pnl_bps |   holdout_min_trade_net_pnl_bps |   holdout_max_trade_net_pnl_bps |   holdout_max_hold_sec | full_basic_gate_screen   | design_positive_screen   | holdout_positive_screen   |   rank_design_total_net_pnl |
|:------------|-------------------:|-----------:|---------:|-------:|-----------:|-------------------:|--------------------:|-------------------:|------------------------:|------------------------:|---------------:|----------------:|--------------:|------------------:|--------------------------:|---------------------------:|--------------------------:|-------------------------------:|-------------------------------:|----------------------:|-----------------:|---------------:|-------------------:|---------------------------:|----------------------------:|---------------------------:|--------------------------------:|--------------------------------:|-----------------------:|:-------------------------|:-------------------------|:--------------------------|----------------------------:|
| reversal    |               1080 |     0.99   |       18 |     18 |   1        |           1        |           1287      |           71.5     |                  71.5   |                    71.5 |          33600 |               6 |             6 |                 1 |                         1 |                      429   |                      71.5 |                           71.5 |                           71.5 |                 33600 |               12 |             12 |           1        |                   1        |                     858     |                    71.5    |                          71.5   |                            71.5 |                  23220 | True                     | True                     | True                      |                           1 |
| reversal    |                720 |     0.99   |       18 |     18 |   1        |           1        |           1287      |           71.5     |                  71.5   |                    71.5 |          77820 |               5 |             5 |                 1 |                         1 |                      357.5 |                      71.5 |                           71.5 |                           71.5 |                 19200 |               13 |             13 |           1        |                   1        |                     929.5   |                    71.5    |                          71.5   |                            71.5 |                  77820 | True                     | True                     | True                      |                           2 |
| reversal    |               1440 |     0.99   |       14 |     13 |   0.928571 |           0.928571 |            741.999  |           52.9999  |                -187.501 |                    71.5 |          86400 |               5 |             5 |                 1 |                         1 |                      357.5 |                      71.5 |                           71.5 |                           71.5 |                 13980 |                9 |              8 |           0.888889 |                   0.888889 |                     384.499 |                    42.7221 |                        -187.501 |                            71.5 |                  86400 | True                     | True                     | False                     |                           3 |
| reversal    |               2880 |     0.99   |       12 |     11 |   0.916667 |           0.916667 |            618.622  |           51.5518  |                -167.878 |                    71.5 |          86400 |               5 |             5 |                 1 |                         1 |                      357.5 |                      71.5 |                           71.5 |                           71.5 |                  6420 |                7 |              6 |           0.857143 |                   0.857143 |                     261.122 |                    37.3032 |                        -167.878 |                            71.5 |                  86400 | True                     | True                     | False                     |                           4 |
| reversal    |               2160 |     0.99   |       13 |     12 |   0.923077 |           0.923077 |            -72.9085 |           -5.60835 |                -930.909 |                    71.5 |          86400 |               5 |             5 |                 1 |                         1 |                      357.5 |                      71.5 |                           71.5 |                           71.5 |                  4680 |                8 |              7 |           0.875    |                   0.875    |                    -430.409 |                   -53.8011 |                        -930.909 |                            71.5 |                  86400 | False                    | True                     | False                     |                           5 |
| reversal    |                720 |     0.9925 |       14 |     14 |   1        |           1        |           1001      |           71.5     |                  71.5   |                    71.5 |          56040 |               4 |             4 |                 1 |                         1 |                      286   |                      71.5 |                           71.5 |                           71.5 |                  6300 |               10 |             10 |           1        |                   1        |                     715     |                    71.5    |                          71.5   |                            71.5 |                  56040 | True                     | True                     | True                      |                           6 |
| reversal    |               1080 |     0.9925 |       14 |     14 |   1        |           1        |           1001      |           71.5     |                  71.5   |                    71.5 |          52020 |               4 |             4 |                 1 |                         1 |                      286   |                      71.5 |                           71.5 |                           71.5 |                 48600 |               10 |             10 |           1        |                   1        |                     715     |                    71.5    |                          71.5   |                            71.5 |                  52020 | True                     | True                     | True                      |                           7 |
| reversal    |               1440 |     0.9925 |       12 |     12 |   1        |           1        |            858      |           71.5     |                  71.5   |                    71.5 |          13800 |               4 |             4 |                 1 |                         1 |                      286   |                      71.5 |                           71.5 |                           71.5 |                 13800 |                8 |              8 |           1        |                   1        |                     572     |                    71.5    |                          71.5   |                            71.5 |                   9840 | True                     | True                     | True                      |                           8 |
| reversal    |               1080 |     0.995  |       11 |     11 |   1        |           1        |            786.5    |           71.5     |                  71.5   |                    71.5 |          57060 |               4 |             4 |                 1 |                         1 |                      286   |                      71.5 |                           71.5 |                           71.5 |                 44460 |                7 |              7 |           1        |                   1        |                     500.5   |                    71.5    |                          71.5   |                            71.5 |                  57060 | True                     | True                     | True                      |                           9 |
| reversal    |               1440 |     0.995  |       11 |     11 |   1        |           1        |            786.5    |           71.5     |                  71.5   |                    71.5 |          59340 |               4 |             4 |                 1 |                         1 |                      286   |                      71.5 |                           71.5 |                           71.5 |                  6960 |                7 |              7 |           1        |                   1        |                     500.5   |                    71.5    |                          71.5   |                            71.5 |                  59340 | True                     | True                     | True                      |                          10 |

## Files

- Candidate evaluations: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v60_btcusdc_sparse_tp_design_selector_audit/v60_design_selector_candidate_evaluations.csv`
- Summary JSON: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v60_btcusdc_sparse_tp_design_selector_audit/v60_summary.json`

## Caveat

This split still reuses historical folds. It is stronger than full-period ranking, but weaker than genuinely new BTCUSDC data.
