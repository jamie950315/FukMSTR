# Research V211 Commands

V211 adds a signal-provenance gate on top of V205 execution validation. It blocks manual, synthetic, backtest, unknown, or blank signal/market sources from satisfying the execution-evidence path.

V211 does not change strategy thresholds, trade direction, leverage logic, or entry/exit logic. It does not place live orders.

## Run Tests

```bash
make test-btcusdc-v211
```

## Run Signal Provenance Gate

```bash
make btcusdc-v211-signal-provenance-gate
```

Optional custom evidence paths:

```bash
PYTHONPATH=src python scripts/run_btcusdc_v211_signal_provenance_gate.py \
  --fills runs/research_v205_execution_validation/fill_audit.csv \
  --kill-switch-events runs/research_v205_execution_validation/kill_switch_events.csv
```

## Outputs

```text
runs/research_v211_signal_provenance_gate/v211_signal_provenance_gate_summary.json
reports/RESEARCH_V211_BTCUSDC_SIGNAL_PROVENANCE_GATE.md
```

## Real-Money Status

V211 alone never promotes real-money use. Real-money use remains blocked until V204 passes with current forward evidence, execution validation, signal provenance, kill-switch evidence, and clean repository secret scanning.
