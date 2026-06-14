# Research V12 Results

V12 continues the long-window branch after V11.  The goal was to keep the strict single-day gate intact and try to turn the best H90 lead into a gate pass without using future price columns, validation-oracle template choice, or replacement trades after a veto.

## Main result

V12 found a **single-day H90 slot-veto research pass**.

```text
run: runs/research_v12_slot_veto_h90_ofi_l5_q90
source ensemble: runs/research_v09_ensemble_h90_5fold_stationary
horizon: 90s
base signal: normal probability edge, threshold 0.1
veto: keep only scheduled slots where ofi_sum_l5_norm <= fold calibration 90th percentile
execution: taker bid/ask, non-overlap
latency: 0.5s
cost: 1.5 bps
```

The key design change is **slot-preserving veto execution**:

1. The model first creates the same non-overlapping H90 probability-edge slot schedule.
2. The OFI veto is applied only to those scheduled slots.
3. Rejected slots still reserve the cooldown interval; the simulator does not replace a vetoed slot with a later overlapping opportunity.

This matters because a normal pre-entry filter can accidentally cherry-pick replacement trades after skipping an entry.  V12 intentionally avoids that advantage.

## Gate result

| Check | Result |
|---|---:|
| Gate passed | true |
| OOF trades | 21 |
| Hit rate | 52.38% |
| Mean net PnL | +7.1647 bps/trade |
| Total net PnL | +150.4583 bps |
| Worst fold mean PnL | +4.5117 bps/trade |
| Worst fold total PnL | +16.8734 bps |
| Aggregate bootstrap mean p05 | +2.3167 bps |
| Stress min mean PnL | +3.5125 bps/trade |
| Stress min total PnL | +73.7624 bps |
| Shift-null p(total >= actual) | 0.0000 |
| Shift-null p(mean >= actual) | 0.0000 |
| Family-null p(total >= selected) | 0.0000 |
| Family-null p(mean >= selected) | 0.0875 |
| Constrained family-null p(total >= selected) | 0.0000 |
| Constrained family-null p(mean >= selected) | 0.0000 |

The gate configuration is recorded in `runs/research_v12_slot_veto_h90_ofi_l5_q90/summary.json`:

```json
{
  "min_oof_trades": 20,
  "min_periods_with_trades": 5,
  "min_period_mean_net_bps": 0.0,
  "min_bootstrap_p05_bps": 0.0,
  "max_shift_null_p_total": 0.1,
  "max_shift_null_p_mean": 0.1,
  "max_family_null_p_total": 0.05,
  "max_family_null_p_mean": 0.1,
  "require_stress_gate": true
}
```

## Fold metrics

| Fold | Threshold | Trades | Hit rate | Mean net PnL | Total net PnL | Bootstrap p05 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.730632 | 5 | 60.00% | +12.9923 | +64.9617 | -0.5547 |
| 2 | 0.572864 | 5 | 40.00% | +5.1882 | +25.9410 | +2.9703 |
| 3 | 0.488206 | 5 | 40.00% | +4.5117 | +22.5584 | +3.8788 |
| 4 | 0.320319 | 3 | 66.67% | +5.6245 | +16.8734 | +5.6245 |
| 5 | 0.309743 | 3 | 66.67% | +6.7080 | +20.1239 | -1.2367 |

Fold-level bootstrap p05 is still negative for folds 1 and 5 because each fold has only 3-5 trades.  The V12 gate uses aggregate bootstrap plus positive fold mean/total, not per-fold bootstrap p05.

## Stress result

The fixed selected signal was repriced under 12 cost/latency combinations:

```text
cost bps: 1.5, 3.0, 5.0
latency sec: 0, 0.5, 1.0, 2.0
```

All 12 cells stayed positive.  The weakest cell was 5 bps cost and 2 seconds latency:

```text
trades: 21
mean net PnL: +3.5125 bps/trade
total net PnL: +73.7624 bps
```

## Family-null correction

V12 ran a small OFI-slot family null:

```text
columns: ofi_sum_l3_norm, ofi_sum_l5_norm, ofi_sum_l10_norm
quantiles: 0.5, 0.6, 0.7, 0.8, 0.9
candidate count: 15
family shift runs: 80
```

The selected candidate is also the top total-PnL candidate in this family:

```text
ofi_sum_l5_norm <= fold calibration q0.9
trades: 21
mean: +7.1647 bps
trades total: +150.4583 bps
```

Family-null p-values:

```text
p_family_max_total_ge_selected: 0.0000
p_family_max_mean_ge_selected: 0.0875
p_family_constrained_max_total_ge_selected: 0.0000
p_family_constrained_max_mean_ge_selected: 0.0000
```

The unconstrained family mean p-value is below the V12 threshold of 0.10 but above 0.05.  If the gate is tightened to require unconstrained family-wise mean p <= 0.05, this lead fails.  The constrained family-null test requires at least 20 trades, matching the strategy gate, and it passes.

## Why this improved V11

V11 H90 source-rank had one losing fold:

```text
fold 4 total: -9.9034 bps
fold 4 mean: -1.9807 bps/trade
```

The OFI slot-veto removes the high positive-OFI scheduled slots that were hurting the later folds while preserving the original non-overlap slot schedule.  Fold 4 becomes:

```text
fold 4 total: +16.8734 bps
fold 4 mean: +5.6245 bps/trade
```

## Current status

```text
single-day leak-free H90 slot-veto gate: passed
single-day stress gate: passed
single-day shifted-signal null: passed
single-day OFI-family null: passed under V12 thresholds
multi-day stability gate: not tested
live deployment gate: not established
```

This is the first post-leakfix long-window research gate pass in the project.  It is still a single-day, 21-trade result.  It should be treated as a promising research candidate, not as evidence of stable profit.

## Next research path

The next required step is multi-day data.  The exact V12 slot-veto workflow should be run as:

```text
past day/session calibrates the OFI threshold
future day/session validates the fixed slot-veto rule
no validation-ranked candidate choice
family-wise null remains active
```

Promotion criteria for a deployable claim should require at least 20 independent sessions, 100+ non-overlap trades, positive session-level aggregate, positive bootstrap p05, and family-wise p-values that remain <= 0.05 under the same predeclared family.
