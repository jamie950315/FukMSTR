# Research V17 Results — Execution Profit-Lock Certificate

V17 continues from the V16 frozen-policy certificate. The V15/V16 entry policy is unchanged; the only promoted change is a slot-preserving take-profit exit lock.

Main run:

```text
runs/research_v17_execution_profit_lock_alpha0125_tp40
```

Frozen entry policy:

```text
alpha = 0.125
edge threshold = 0.1
OFI veto = ofi_sum_l5_norm <= fold calibration q0.9
K-line guard = directional signal * kline_15s_rv_6_bps >= fold calibration q0.0
horizon = 90s
cost = 1.5 bps
latency = 0.5s
```

New V17 execution lock:

```text
take_profit_bps = 40.0
stop_loss_bps = 0.0
reserve_horizon = true
```

A take-profit exit can close a trade early, but the original 90-second slot remains reserved. This means the exit lock cannot create new overlapping entries or harvest extra cooldown slots.

## Gate result

| Metric | Result |
|---|---:|
| Gate passed | true |
| Trades | 20 |
| Hit rate | 65.00% |
| Mean net PnL | +10.1404 bps/trade |
| Median net PnL | +7.2323 bps/trade |
| Total net PnL | +202.8090 bps |
| Profit factor | 6.7816 |
| Max drawdown | -12.6208 bps |
| Take-profit exits | 3 |
| Horizon exits | 17 |
| Mean hold time | 85.2279 sec |
| Worst fold mean | +4.5117 bps/trade |
| Worst fold total | +16.8734 bps |
| Bootstrap mean p05 | +4.6097 bps/trade |
| Bootstrap total p05 | +92.1944 bps |
| Full severe stress min mean | +0.4911 bps/trade |
| Full severe stress min total | +9.8225 bps |
| Full union add-one p(total) | 0.000999 |
| Full union add-one p(mean) | 0.001998 |

## Comparison versus V16

| Metric                    | v16 frozen entry   | v17 exit lock   |
|:--------------------------|:-------------------|:----------------|
| Trades                    | 20                 | 20              |
| Hit rate                  | 65.00%             | 65.00%          |
| Mean net PnL bps/trade    | +9.4640            | +10.1404        |
| Total net PnL bps         | +189.2795          | +202.8090       |
| Bootstrap mean p05 bps    | +4.7174            | +4.6097         |
| Full-stress min mean bps  | -0.1859            | +0.4911         |
| Full-stress min total bps | -3.7186            | +9.8225         |

The key V17 upgrade is that the full severe stress grid now stays positive, including the previous failing `10 bps / 5 sec` corner.

## Fold metrics

|   fold |   trades |   hit_rate |   mean_net_pnl_bps |   total_net_pnl_bps |   take_profit_exits |   horizon_exits |
|-------:|---------:|-----------:|-------------------:|--------------------:|--------------------:|----------------:|
|      1 |        4 |   0.75     |           23.3765  |             93.5062 |                   2 |               2 |
|      2 |        5 |   0.8      |            9.94943 |             49.7472 |                   1 |               4 |
|      3 |        5 |   0.4      |            4.51167 |             22.5584 |                   0 |               5 |
|      4 |        3 |   0.666667 |            5.62445 |             16.8734 |                   0 |               3 |
|      5 |        3 |   0.666667 |            6.70796 |             20.1239 |                   0 |               3 |

## Worst severe stress cells

|   cost_bps |   latency_sec |   trades |   hit_rate |   mean_net_pnl_bps |   total_net_pnl_bps |   max_drawdown_bps |   take_profit_exits |
|-----------:|--------------:|---------:|-----------:|-------------------:|--------------------:|-------------------:|--------------------:|
|         10 |           5   |       20 |       0.45 |           0.491123 |             9.82247 |           -54.337  |                   3 |
|         10 |           1   |       20 |       0.45 |           1.56085  |            31.2169  |           -43.6584 |                   3 |
|         10 |           0.5 |       20 |       0.45 |           1.64045  |            32.809   |           -43.6584 |                   3 |
|         10 |           3   |       20 |       0.45 |           1.64054  |            32.8108  |           -42.8655 |                   3 |
|         10 |           2   |       20 |       0.45 |           1.75989  |            35.1979  |           -43.6584 |                   3 |
|         10 |           0   |       20 |       0.45 |           1.87896  |            37.5793  |           -43.6584 |                   3 |

Stress grid:

```text
costs = 1.5, 3.0, 5.0, 7.5, 10.0 bps
latencies = 0.0, 0.5, 1.0, 2.0, 3.0, 5.0 sec
cells = 30
all cells positive = true
```

The worst cell is cost 10 bps and latency 5 seconds:

```text
mean = +0.4911 bps/trade
total = +9.8225 bps
```

## 1000-shift add-one family nulls

| Family                 |   Candidates |   add-one p(total) |   add-one p(mean) |   Null max total |   Null max mean |   Exceed total |   Exceed mean |
|:-----------------------|-------------:|-------------------:|------------------:|-----------------:|----------------:|---------------:|--------------:|
| Selected only          |            1 |           0.000999 |          0.000999 |          81.6562 |          5.0147 |              0 |             0 |
| Alpha family           |            7 |           0.000999 |          0.000999 |         116.581  |          7.661  |              0 |             0 |
| OFI family             |           15 |           0.000999 |          0.000999 |         117.976  |          9.4667 |              0 |             0 |
| K-line family          |            7 |           0.000999 |          0.000999 |         119.887  |          7.3332 |              0 |             0 |
| Exit family            |            6 |           0.000999 |          0.000999 |          95.6786 |          6.8342 |              0 |             0 |
| Signal union           |           27 |           0.000999 |          0.000999 |         119.887  |          9.4667 |              0 |             0 |
| Full signal/exit union |          162 |           0.000999 |          0.001998 |         139.797  |         10.1729 |              0 |             1 |

The strictest V17 p-value is the full signal/exit union mean p-value:

```text
p_addone(mean) = 0.001998
```

This is based on 1000 shifted-signal runs with add-one correction. One full-union shifted path exceeded the selected mean, and zero exceeded the selected total.

## Stability checks

```text
5 equal-trade blocks positive: 5 / 5
10 pair blocks positive: 10 / 10
Top 5 winners removed total: +30.6096 bps
Top 7 winners removed total: +1.8937 bps
Leave-one-trade-out min total: +155.0048 bps
Leave-one-fold-out min total: +109.3028 bps
```

## New files

```text
src/lob_microprice_lab/exit_lock.py
src/lob_microprice_lab/profit_execution_lock.py
scripts/run_profit_execution_lock_v17.py
tests/test_exit_lock_v17.py
tests/test_profit_execution_lock_v17.py
docs/RESEARCH_V17_COMMANDS.md
reports/RESEARCH_V17_RESULTS.md
runs/research_v17_execution_profit_lock_alpha0125_tp40/
runs/research_v17_summary.csv
```

## Status

```text
V15/V16 frozen entry reproduced: yes
slot-preserving take-profit exit lock: passed
1000-shift add-one selected null: passed
1000-shift add-one alpha family: passed
1000-shift add-one OFI family: passed
1000-shift add-one K-line family: passed
1000-shift add-one exit family: passed
1000-shift add-one full signal/exit union: passed
full severe stress through 10 bps / 5 sec: passed
single-sample research profit-lock target: passed
true independent multi-day live stable profit: not established from bundled data alone
```

V17 is the strongest single-sample research certificate so far. The remaining blocker for a real stable-profit claim is unchanged: this exact frozen policy must pass independent multi-day validation without further tuning.
