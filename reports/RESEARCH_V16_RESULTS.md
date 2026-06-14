# Research V16 Results — Frozen V15 Profit-Lock Certificate

V16 continues from the v15 promoted K-line support-guard policy. It is **not** a new signal-tuning pass: alpha, OFI veto, K-line guard feature, K-line quantile, horizon, cost, and latency remain frozen. The new research layer is a stronger audit certificate around the same policy.

Main run:

```text
runs/research_v16_profit_lock_certificate_alpha0125
```

Frozen policy:

```text
alpha = 0.125
edge threshold = 0.1
OFI veto = ofi_sum_l5_norm <= fold calibration q0.9
K-line guard = directional signal * kline_15s_rv_6_bps >= fold calibration q0.0
horizon = 90s
cost = 1.5 bps
latency = 0.5s
execution = taker bid/ask, non-overlap
```

## V16 gate result

| Metric | Result |
|---|---:|
| Gate passed | true |
| Trades | 20 |
| Hit rate | 65.00% |
| Mean net PnL | +9.4640 bps/trade |
| Total net PnL | +189.2795 bps |
| Worst fold mean | +4.5117 bps/trade |
| Worst fold total | +16.8734 bps |
| Bootstrap mean p05 | +4.7174 bps/trade |
| Bootstrap total p05 | +94.3476 bps |
| Leave-one-trade-out min total | +143.8461 bps |
| Leave-one-fold-out min total | +114.8711 bps |
| Remove top 5 winners total | +30.6096 bps |
| Remove top 7 winners total | +1.8937 bps |
| Primary stress min mean | +2.3141 bps/trade |
| Primary stress min total | +46.2814 bps |
| Secondary stress min mean | +0.8043 bps/trade |
| Secondary stress min total | +16.0868 bps |
| Absolute all-stress min mean | -0.1859 bps/trade |
| Absolute all-stress min total | -3.7186 bps |

## What changed versus v15

V15 already had the better trading rule. V16 does **not** increase raw PnL; it improves the evidence quality:

- shifted-signal nulls increased from 40 runs to 1000 sparse runs
- p-values now use add-one accounting, so zero-exceed results become 1 / 1001 instead of 0
- family-wise corrections cover selected-only, alpha, OFI, K-line, and triple-union families
- stress grid expands to 30 cells: costs 1.5, 3, 5, 7.5, 10 bps and latency 0, 0.5, 1, 2, 3, 5 seconds
- winner-dependence diagnostics are explicit: top-winner removal, leave-one-trade-out, leave-one-fold-out

## Comparison

| Metric | v12 OFI slot-veto | v14 alpha=0.125 | v15 support guard | v16 certificate |
|---|---:|---:|---:|---:|
| Trades | 21 | 23 | 20 | 20 |
| Hit rate | 52.38% | 56.52% | 65.00% | 65.00% |
| Mean net PnL bps/trade | +7.1647 | +7.4131 | +9.4640 | +9.4640 |
| Total net PnL bps | +150.4583 | +170.5013 | +189.2795 | +189.2795 |
| Worst fold mean bps | +4.5117 | +2.2604 | +4.5117 | +4.5117 |
| Bootstrap mean p05 bps | +2.3167 | +3.1505 | +4.5357 | +4.7174 |


## 1000-shift add-one family nulls

| Family | add-one p(total) | add-one p(mean) | null max total bps | null max mean bps | exceed total | exceed mean |
|---|---:|---:|---:|---:|---:|---:|
| Selected only | 0.000999 | 0.000999 | +87.7006 | +4.8723 | 0 | 0 |
| Alpha family | 0.000999 | 0.000999 | +120.6487 | +7.8266 | 0 | 0 |
| OFI family | 0.000999 | 0.001998 | +131.7408 | +9.9068 | 0 | 1 |
| K-line family | 0.000999 | 0.000999 | +107.1613 | +6.2396 | 0 | 0 |
| Triple union | 0.000999 | 0.001998 | +131.7408 | +9.9068 | 0 | 1 |


The strictest V16 family result is the OFI/triple-union mean p-value:

```text
p_addone(mean) = 0.001998
```

This means 1 of 1000 shifted family null paths had mean PnL greater than or equal to the selected mean, and the reported p-value applies add-one correction: `(1 + 1) / (1000 + 1)`.

## Extended stress

Stress grid:

```text
costs = 1.5, 3.0, 5.0, 7.5, 10.0 bps
latencies = 0.0, 0.5, 1.0, 2.0, 3.0, 5.0 sec
cells = 30
```

Primary operational stress gate:

```text
cost <= 7.5 bps
latency <= 5.0 sec
min mean = +2.3141 bps/trade
min total = +46.2814 bps
passed = true
```

Secondary high-cost stress gate:

```text
cost <= 10.0 bps
latency <= 3.0 sec
min mean = +0.8043 bps/trade
min total = +16.0868 bps
passed = true
```

Absolute full-grid caveat:

```text
worst cell = cost 10.0 bps, latency 5.0 sec
mean = -0.1859 bps/trade
total = -3.7186 bps
```

That extreme cell fails slightly. V16 therefore claims an operational stress pass through 7.5 bps / 5 sec and 10 bps / 3 sec, **not** an all-cell 10 bps / 5 sec pass.

## Winner-dependence diagnostics

The v15/v16 policy remains positive after removing the top 5 winners:

```text
top5 removed total = +30.6096 bps
```

It remains barely positive after removing the top 7 winners:

```text
top7 removed total = +1.8937 bps
```

It turns negative after removing the top 8 winners, so this is still a small-sample result. This is recorded as a research warning rather than hidden.

## New files

```text
src/lob_microprice_lab/profit_lock.py
scripts/run_profit_lock_v16.py
tests/test_profit_lock_v16.py
docs/RESEARCH_V16_COMMANDS.md
reports/RESEARCH_V16_RESULTS.md
runs/research_v16_profit_lock_certificate_alpha0125/
runs/research_v16_summary.csv
```

New CLI and make target:

```bash
python -m lob_microprice_lab.cli profit-lock-certificate --help
make profit-lock-v16
```

## Validation performed

```text
python -m py_compile src/lob_microprice_lab/*.py scripts/run_profit_lock_v16.py: passed
pytest -q tests/test_profit_success_fast_v15.py tests/test_kline_guard_v15.py tests/test_profit_lock_v16.py: 7 passed
python -m lob_microprice_lab.cli profit-lock-certificate --help: passed
make profit-lock-v16: passed
zip integrity: passed
```

The Python environment printed a spreadsheet-runtime warmup warning unrelated to this project, but all commands above returned exit code 0.

## Status

```text
v15 promoted trading policy reproduced: yes
v16 frozen-policy certificate gate: passed
1000-shift add-one family nulls: passed
primary stress gate through 7.5 bps / 5 sec: passed
secondary stress gate through 10 bps / 3 sec: passed
absolute 10 bps / 5 sec stress: failed slightly
true independent multi-day stable profit: not established
live deployment gate: not established
```

The next research step cannot honestly be another retune on this same bundled sample. The next valid step is to lock this V16 policy and run independent multi-day validation.
