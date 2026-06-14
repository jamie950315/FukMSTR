# Research V82 BTCUSDC Signal Inversion Audit Results

## Decision

- Promote inverted signal: `False`
- Failed checks: `total_net_pnl;positive_fold_rate;positive_month_rate;win_rate`

## Gate

- Min total net PnL: `0.0` bps
- Min positive fold rate: `1.0`
- Min positive month rate: `1.0`
- Min win rate: `0.5`

## Original vs Inverted

variant,trades,total_net_pnl_bps,mean_net_pnl_bps,win_rate,fold_count,positive_fold_rate,worst_fold_net_pnl_bps,month_count,positive_month_rate,worst_month_net_pnl_bps
original,9768,-84236.96480717228,-8.623767895902157,0.1373873873873874,5,0.0,-22721.801061415394,30,0.0,-3268.9193234126788
inverted_signal,9768,-81819.03519282774,-8.376232104097843,0.14260851760851762,5,0.0,-22566.198938584606,30,0.0,-3153.4571155558747

## Interpretation

V82 tests whether the failed BTCUSDC public replay was simply a wrong-side signal. The inverted variant flips gross PnL and subtracts the same execution cost again, so it does not get free fees or free spread. Both original and inverted variants remain negative across every fold and every month.

The result does not promote a strategy route. It closes the simple signal-inversion rescue idea: the issue is not just that long/short sides were swapped.
