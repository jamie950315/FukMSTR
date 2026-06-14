# Research V66 Design-Robust Selector Results

## Purpose

V66 ranks the V59 parameter neighborhood by dense entry-delay robustness on design folds only, then evaluates the selected candidate on holdout folds.

The TP80 exit, no-stop policy, V26 contract gate settings, and V59 parameter grid are unchanged.

## Design-Robust Selected Candidate

- Direction: `reversal`
- Lookback minutes: `1440`
- Quantile: `0.99`
- Design pass count: `117/121`
- Design fail ranges: `90,92-94`
- Design min total net pnl: `1.436218` bps
- Same as V60 design-total candidate: `False`

## Holdout Dense Gate Result For Design-Robust Candidate

- Holdout gate pass count: `0/121`
- Holdout fail ranges: `0-120`
- Worst holdout delay: `119`
- Worst holdout account return: `18.466092%`

## V60 Candidate Holdout Reference

- V60 holdout gate pass count: `111/121`
- V60 holdout fail ranges: `5,109-110,112-113,116-120`

## Top 10 Design-Robust Candidates

| direction   |   lookback_minutes |   quantile | rule_name               |   design_base_entry_count |   delay_count |   pass_count |   fail_count |   pass_rate | fail_delay_ranges   |   worst_delay |   min_total_net_pnl_bps |   mean_total_net_pnl_bps |   min_trade_net_pnl_bps |   rank_design_delay_robust |
|:------------|-------------------:|-----------:|:------------------------|--------------------------:|--------------:|-------------:|-------------:|------------:|:--------------------|--------------:|------------------------:|-------------------------:|------------------------:|---------------------------:|
| reversal    |               1440 |     0.99   | reversal_lb1440_q0p9900 |                         5 |           121 |          117 |            4 |    0.966942 | 90,92-94            |            93 |                 1.43622 |                  346.187 |                -284.564 |                          1 |
| reversal    |               2160 |     0.99   | reversal_lb2160_q0p9900 |                         5 |           121 |          117 |            4 |    0.966942 | 89,91-93            |            92 |                 1.43622 |                  346.187 |                -284.564 |                          2 |
| reversal    |               2880 |     0.99   | reversal_lb2880_q0p9900 |                         5 |           121 |          117 |            4 |    0.966942 | 90,92-94            |            93 |                 1.43622 |                  346.187 |                -284.564 |                          3 |
| reversal    |               1080 |     0.995  | reversal_lb1080_q0p9950 |                         4 |           121 |          117 |            4 |    0.966942 | 90,92-94            |            93 |               -70.0638  |                  274.687 |                -284.564 |                          4 |
| reversal    |               1080 |     0.9975 | reversal_lb1080_q0p9975 |                         4 |           121 |          117 |            4 |    0.966942 | 89,91-93            |            92 |               -70.0638  |                  274.687 |                -284.564 |                          5 |
| reversal    |               1440 |     0.9925 | reversal_lb1440_q0p9925 |                         4 |           121 |          117 |            4 |    0.966942 | 90,92-94            |            93 |               -70.0638  |                  274.687 |                -284.564 |                          6 |
| reversal    |               1440 |     0.995  | reversal_lb1440_q0p9950 |                         4 |           121 |          117 |            4 |    0.966942 | 89,91-93            |            92 |               -70.0638  |                  274.687 |                -284.564 |                          7 |
| reversal    |                720 |     0.995  | reversal_lb720_q0p9950  |                         3 |           121 |          117 |            4 |    0.966942 | 93,95-97            |            96 |              -141.564   |                  203.187 |                -284.564 |                          8 |
| reversal    |               1440 |     0.9975 | reversal_lb1440_q0p9975 |                         3 |           121 |          117 |            4 |    0.966942 | 89,91-93            |            92 |              -141.564   |                  203.187 |                -284.564 |                          9 |
| reversal    |               2160 |     0.9925 | reversal_lb2160_q0p9925 |                         3 |           121 |          117 |            4 |    0.966942 | 89,91-93            |            92 |              -141.564   |                  203.187 |                -284.564 |                         10 |

## Selected Holdout Pass/Fail Ranges

| value   |   start |   end |   count |
|:--------|--------:|------:|--------:|
| False   |       0 |   120 |     121 |

## Selected Holdout Worst 10 Delays

|   entry_delay_min |   entry_count | gate_passed   | failed_checks                                                            |   trades |   win_rate |   total_bps |   mean_bps |   min_trade_bps |   max_drawdown_bps |   account_return_pct |   account_max_drawdown_pct |   missed_trade_p05_account_return_pct |   extra_cost_account_return_pct |   promoted_loss_min_account_return_pct |   promoted_loss_worst_drawdown_pct |   fold_min_total_net_pnl_bps |   blocks5_min_total_net_pnl_bps |   blocks10_min_total_net_pnl_bps |
|------------------:|--------------:|:--------------|:-------------------------------------------------------------------------|---------:|-----------:|------------:|-----------:|----------------:|-------------------:|---------------------:|---------------------------:|--------------------------------------:|--------------------------------:|---------------------------------------:|-----------------------------------:|-----------------------------:|--------------------------------:|---------------------------------:|
|                62 |             9 | False         | trade_count;win_rate;missed_trade_account_return;synthetic_loss_drawdown |        9 |   0.888889 |     324.67  |    36.0744 |        -247.33  |           -247.33  |              18.4661 |                   -19.7864 |                              -8.34641 |                         14.4536 |                                8.06609 |                           -22.3864 |                     -175.83  |                        -175.83  |                         -247.33  |
|                61 |             9 | False         | trade_count;win_rate;missed_trade_account_return;synthetic_loss_drawdown |        9 |   0.888889 |     336.227 |    37.3586 |        -235.773 |           -235.773 |              19.3907 |                   -18.8618 |                              -7.42184 |                         15.3782 |                                8.99066 |                           -21.4618 |                     -164.273 |                        -164.273 |                         -235.773 |
|                51 |             9 | False         | trade_count;win_rate;missed_trade_account_return;synthetic_loss_drawdown |        9 |   0.888889 |     336.786 |    37.4207 |        -235.214 |           -235.214 |              19.4354 |                   -18.8171 |                              -7.37709 |                         15.4229 |                                9.03541 |                           -21.4171 |                     -163.714 |                        -163.714 |                         -235.214 |
|                63 |             9 | False         | trade_count;win_rate;missed_trade_account_return;synthetic_loss_drawdown |        9 |   0.888889 |     339.919 |    37.7688 |        -232.081 |           -232.081 |              19.686  |                   -18.5665 |                              -7.12647 |                         15.6735 |                                9.28603 |                           -21.1665 |                     -160.581 |                        -160.581 |                         -232.081 |
|                50 |             9 | False         | trade_count;win_rate;missed_trade_account_return;synthetic_loss_drawdown |        9 |   0.888889 |     340.362 |    37.818  |        -231.638 |           -231.638 |              19.7215 |                   -18.531  |                              -7.091   |                         15.709  |                                9.3215  |                           -21.131  |                     -160.138 |                        -160.138 |                         -231.638 |
|                47 |             9 | False         | trade_count;win_rate;missed_trade_account_return;synthetic_loss_drawdown |        9 |   0.888889 |     340.62  |    37.8467 |        -231.38  |           -231.38  |              19.7421 |                   -18.5104 |                              -7.07037 |                         15.7296 |                                9.34213 |                           -21.1104 |                     -159.88  |                        -159.88  |                         -231.38  |
|                49 |             9 | False         | trade_count;win_rate;missed_trade_account_return;synthetic_loss_drawdown |        9 |   0.888889 |     343.173 |    38.1304 |        -228.827 |           -228.827 |              19.9464 |                   -18.3061 |                              -6.86613 |                         15.9339 |                                9.54637 |                           -20.9061 |                     -157.327 |                        -157.327 |                         -228.827 |
|                65 |             9 | False         | trade_count;win_rate;missed_trade_account_return;synthetic_loss_drawdown |        9 |   0.888889 |     347.796 |    38.644  |        -224.204 |           -224.204 |              20.3162 |                   -17.9363 |                              -6.49629 |                         16.3037 |                                9.91621 |                           -20.5363 |                     -152.704 |                        -152.704 |                         -224.204 |
|                54 |             9 | False         | trade_count;win_rate;missed_trade_account_return;synthetic_loss_drawdown |        9 |   0.888889 |     348.006 |    38.6674 |        -223.994 |           -223.994 |              20.333  |                   -17.9195 |                              -6.4795  |                         16.3205 |                                9.933   |                           -20.5195 |                     -152.494 |                        -152.494 |                         -223.994 |
|                52 |             9 | False         | trade_count;win_rate;missed_trade_account_return;synthetic_loss_drawdown |        9 |   0.888889 |     348.214 |    38.6905 |        -223.786 |           -223.786 |              20.3496 |                   -17.9029 |                              -6.46285 |                         16.3371 |                                9.94965 |                           -20.5029 |                     -152.286 |                        -152.286 |                         -223.786 |

## Files

- Design candidate robustness CSV: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v66_btcusdc_sparse_tp_design_robust_selector/v66_design_delay_robust_candidate_rankings.csv`
- Selected holdout delay scan CSV: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v66_btcusdc_sparse_tp_design_robust_selector/v66_selected_holdout_dense_delay_contract_gate_summary.csv`
- V60 holdout delay scan CSV: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v66_btcusdc_sparse_tp_design_robust_selector/v66_v60_reference_holdout_dense_delay_contract_gate_summary.csv`
- Summary JSON: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v66_btcusdc_sparse_tp_design_robust_selector/v66_summary.json`

## Caveat

This avoids selecting on holdout, but it is still historical BTCUSDC data and not future unseen validation.
