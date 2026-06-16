# Research V212 Commands

V212 adds a forward-freshness gate on top of V90 forward monitoring. It blocks stale V90 data and current no-signal V90 runs from being treated as real-money forward validation.

V212 does not change strategy thresholds, trade direction, leverage logic, or entry/exit logic. It does not place live orders.

## Run Tests

```bash
make test-btcusdc-v212
```

## Run Forward Freshness Gate

```bash
make btcusdc-v212-forward-freshness-gate
```

## Outputs

```text
runs/research_v212_forward_freshness_gate/v212_forward_freshness_gate_summary.json
reports/RESEARCH_V212_BTCUSDC_FORWARD_FRESHNESS_GATE.md
```

## Real-Money Status

V212 alone never promotes real-money use. Real-money use remains blocked until V204 passes with current forward evidence, execution validation, signal provenance, kill-switch evidence, and clean repository secret scanning.
