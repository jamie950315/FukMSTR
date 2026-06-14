# Research V59 Neighborhood Audit Results

## Purpose

V59 checks whether the fixed V55/V57 sparse BTCUSDC rule is isolated within a nearby parameter family.

This is an audit only. It does not promote or replace the V55/V57 fixed rule.

## Fixed Components

- Bars: Binance public 1m kline cache
- Entry: next open
- Exit: TP80, no stop loss
- Horizon reserve: 1440 minutes
- Feature: abs_return_bps

## Grid

- Lookbacks: `[720, 1080, 1440, 2160, 2880]`
- Quantiles: `[0.99, 0.9925, 0.995, 0.9975, 0.999]`
- Directions: `['reversal', 'momentum']`
- Total candidates: `50`

## Selected Rule Position

- Selected rule rank by total pnl: `8`
- Selected trades: `11`
- Selected wins: `11`
- Selected win rate: `1.000000`
- Selected total net pnl: `786.500000` bps
- Selected basic gate screen: `True`

## Family Summary

- Basic gate screen pass count: `11`
- Candidates with 11 wins: `15`
- Candidates matching selected total pnl or better: `8`
- Reversal basic gate pass count: `10`
- Momentum basic gate pass count: `1`

## Top 10 By Total Pnl

| direction   |   lookback_minutes |   quantile |   trades |   wins |   win_rate |   take_profit_rate |   total_net_pnl_bps |   mean_net_pnl_bps |   min_trade_net_pnl_bps |   max_trade_net_pnl_bps |   max_hold_sec | basic_gate_screen   |   rank_total_net_pnl |
|:------------|-------------------:|-----------:|---------:|-------:|-----------:|-------------------:|--------------------:|-------------------:|------------------------:|------------------------:|---------------:|:--------------------|---------------------:|
| reversal    |                720 |     0.99   |       18 |     18 |   1        |           1        |            1287     |            71.5    |                  71.5   |                    71.5 |          77820 | True                |                    1 |
| reversal    |               1080 |     0.99   |       18 |     18 |   1        |           1        |            1287     |            71.5    |                  71.5   |                    71.5 |          33600 | True                |                    2 |
| reversal    |                720 |     0.9925 |       14 |     14 |   1        |           1        |            1001     |            71.5    |                  71.5   |                    71.5 |          56040 | True                |                    3 |
| reversal    |               1080 |     0.9925 |       14 |     14 |   1        |           1        |            1001     |            71.5    |                  71.5   |                    71.5 |          52020 | True                |                    4 |
| reversal    |               1440 |     0.9925 |       12 |     12 |   1        |           1        |             858     |            71.5    |                  71.5   |                    71.5 |          13800 | True                |                    5 |
| reversal    |                720 |     0.995  |       11 |     11 |   1        |           1        |             786.5   |            71.5    |                  71.5   |                    71.5 |          52440 | True                |                    6 |
| reversal    |               1080 |     0.995  |       11 |     11 |   1        |           1        |             786.5   |            71.5    |                  71.5   |                    71.5 |          57060 | True                |                    7 |
| reversal    |               1440 |     0.995  |       11 |     11 |   1        |           1        |             786.5   |            71.5    |                  71.5   |                    71.5 |          59340 | True                |                    8 |
| reversal    |               1440 |     0.99   |       14 |     13 |   0.928571 |           0.928571 |             741.999 |            52.9999 |                -187.501 |                    71.5 |          86400 | True                |                    9 |
| reversal    |               2160 |     0.9925 |       10 |     10 |   1        |           1        |             715     |            71.5    |                  71.5   |                    71.5 |          38100 | False               |                   10 |

## Files

- Candidate evaluations: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v59_btcusdc_sparse_tp_neighborhood_audit/v59_neighborhood_candidate_evaluations.csv`
- Summary JSON: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v59_btcusdc_sparse_tp_neighborhood_audit/v59_summary.json`

## Caveat

A neighborhood audit can show isolation or nearby support, but it still reuses the same historical sample and does not create more observed trades.
