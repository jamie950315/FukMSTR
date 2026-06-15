# Research V204 Commands

V204 adds a real-money readiness gate. It does not change strategy thresholds,
entry/exit logic, trade side, or leverage rules.

Run the gate:

```bash
make btcusdc-v204-real-money-readiness-gate
```

Run the focused test:

```bash
make test-btcusdc-v204
```

The gate reads:

- `runs/research_v195_post_goal_overfitting_audit/v195_post_goal_overfitting_audit_summary.json`
- `runs/research_v196_forward_monitoring_gate/v196_forward_monitoring_gate_summary.json`
- `runs/paper_v142_realtime_safe_smoke/summary.json`
- `runs/research_v204_real_money_execution_validation/execution_validation_summary.json`

Current expected behavior is to block real-money promotion unless all checks
pass with current evidence.

Outputs:

- `runs/research_v204_real_money_readiness_gate/v204_real_money_readiness_summary.json`
- `reports/RESEARCH_V204_BTCUSDC_REAL_MONEY_READINESS_GATE.md`
