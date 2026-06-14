# Research V15 Results — K-line Support Guard Profit Success Audit

V15 continues from the uploaded V12 lineage through the V14 stability-lock candidate.  It keeps the V14 policy frozen where it matters, then adds one extra slot-preserving K-line support guard and audits the resulting candidate against alpha, OFI, K-line, and combined family-wise shifted-signal nulls.

## Frozen selected policy

```text
base ensemble: runs/research_v09_ensemble_h90_5fold_stationary
kline ensemble: runs/research_v13_kline_h90_5fold_stationary_v12folds
horizon: 90s
cost: 1.5 bps
latency: 0.5s
edge threshold: 0.1
K-line probability alpha: 0.125
OFI veto: ofi_sum_l5_norm <= fold calibration q0.9
K-line support guard: directional signal * kline_15s_rv_6_bps >= fold calibration q0.0
execution: taker bid/ask, non-overlap
```

The K-line guard is slot-preserving: it can only cancel a pre-scheduled V14-style slot.  Cancelled slots still reserve the cooldown window, so the audit cannot skip a losing slot and replace it with a later overlapping winner.

## Aggregate result

| Metric | V15 |
|---|---:|
| Gate passed | True |
| Trades | 20 |
| Hit rate | 65.00% |
| Mean net PnL | 9.4640 bps/trade |
| Total net PnL | 189.2795 bps |
| Worst fold mean | 4.5117 bps/trade |
| Worst fold total | 16.8734 bps |
| Bootstrap mean p05 | 4.5357 bps/trade |
| Bootstrap total p05 | 90.7135 bps |
| Stress min mean | 5.8043 bps/trade |
| Stress min total | 116.0868 bps |
| 5-block min total | 2.7144 bps |
| 10-block min total | 0.9586 bps |
| Leave-one-fold-out min total | 114.8711 bps |
| Selected shift p(total / mean) | 0.0000 / 0.0000 |
| Alpha family p(total / mean) | 0.0000 / 0.0000 |
| OFI family p(total / mean) | 0.0000 / 0.0000 |
| K-line family p(total / mean) | 0.0000 / 0.0000 |
| Union family p(total / mean) | 0.0000 / 0.0000 |

## Improvement versus prior checkpoints

| Metric | V12 OFI slot-veto | V14 alpha=0.125 | V15 support guard |
|---|---:|---:|---:|
| Trades | 21 | 23 | 20 |
| Hit rate | 52.38% | 56.52% | 65.00% |
| Mean net PnL | +7.1647 | +7.4131 | +9.4640 |
| Total net PnL | +150.4583 | +170.5013 | +189.2795 |
| Worst fold mean | +4.5117 | +2.2604 | +4.5117 |
| Worst fold total | +16.8734 | +9.0417 | +16.8734 |
| Stress min mean | +3.5125 | +3.6705 | +5.8043 |
| Stress min total | +73.7624 | +84.4221 | +116.0868 |
| Weakest equal-trade block | not in v12 gate | +0.2558 | +0.9586 |

## Stability blocks

### 5 equal-trade blocks

|   block |   trades |   mean_net_pnl_bps |   total_net_pnl_bps |
|--------:|---------:|-------------------:|--------------------:|
|       1 |        4 |          18.6021   |            74.4083  |
|       2 |        4 |          13.4121   |            53.6485  |
|       3 |        4 |           0.678609 |             2.71444 |
|       4 |        4 |           6.80327  |            27.2131  |
|       5 |        4 |           7.82378  |            31.2951  |

### 10 pair blocks

|   block |   trades |   mean_net_pnl_bps |   total_net_pnl_bps |
|--------:|---------:|-------------------:|--------------------:|
|       1 |        2 |          34.7423   |           69.4846   |
|       2 |        2 |           2.46189  |            4.92378  |
|       3 |        2 |           0.486208 |            0.972416 |
|       4 |        2 |          26.338    |           52.6761   |
|       5 |        2 |           0.479289 |            0.958578 |
|       6 |        2 |           0.877929 |            1.75586  |
|       7 |        2 |          10.7555   |           21.511    |
|       8 |        2 |           2.85105  |            5.70209  |
|       9 |        2 |          14.7697   |           29.5393   |
|      10 |        2 |           0.877901 |            1.7558   |

## Family-wise null correction

```json
{
  "selected_total_net_pnl_bps": 189.27947331175847,
  "selected_mean_net_pnl_bps": 9.463973665587924,
  "shift_null_runs": 40,
  "selected_only": {
    "candidate_count": 1,
    "p_total_ge_selected": 0.0,
    "p_mean_ge_selected": 0.0,
    "null_total_p95_bps": 45.70073859485876,
    "null_mean_p95_bps": 2.6979210828373175,
    "null_total_max_bps": 62.75223250176091,
    "null_mean_max_bps": 3.486235138986717
  },
  "alpha_family": {
    "candidate_count": 7,
    "p_total_ge_selected": 0.0,
    "p_mean_ge_selected": 0.0,
    "null_total_p95_bps": 62.93532749776859,
    "null_mean_p95_bps": 3.8743265611434916,
    "null_total_max_bps": 86.54379785150388,
    "null_mean_max_bps": 5.711308587377878
  },
  "ofi_family": {
    "candidate_count": 15,
    "p_total_ge_selected": 0.0,
    "p_mean_ge_selected": 0.0,
    "null_total_p95_bps": 79.98582009609311,
    "null_mean_p95_bps": 5.915362270291403,
    "null_total_max_bps": 95.94095871371735,
    "null_mean_max_bps": 6.912573734416753
  },
  "kline_family": {
    "candidate_count": 7,
    "p_total_ge_selected": 0.0,
    "p_mean_ge_selected": 0.0,
    "null_total_p95_bps": 68.83152784328978,
    "null_mean_p95_bps": 3.823973769071654,
    "null_total_max_bps": 112.76485459189833,
    "null_mean_max_bps": 6.58984742216206
  },
  "triple_union_family": {
    "candidate_count": 27,
    "p_total_ge_selected": 0.0,
    "p_mean_ge_selected": 0.0,
    "null_total_p95_bps": 95.30970235963514,
    "null_mean_p95_bps": 6.603001332174375,
    "null_total_max_bps": 112.76485459189833,
    "null_mean_max_bps": 6.912573734416753
  }
}
```

The selected result beats the selected-only shifted null, alpha family, OFI family, K-line family, and combined alpha/OFI/K-line union family under the configured p <= 0.05 gate.

## Reproduce

```bash
make profit-success-fast-v15
```

## Status

```text
single-sample research profit-success gate: passed
alpha-family correction: passed
OFI-family correction: passed
K-line-family correction: passed
triple-union family correction: passed
stress gate: passed
true independent multi-day stable profit: not established from bundled data alone
```

The remaining blocker is not model code; it is independent multi-day data.  The selected V15 policy should now be frozen before any future multi-day validation.
