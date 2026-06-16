# Research V220 Commands

V220 hardens execution evidence validation. V205 now rejects otherwise clean fill evidence when the latest execution timestamp is older than the allowed evidence age, and V204/V206/CLI require that recency check before any real-money launch path can pass.

V220 does not place live orders, tune thresholds, change entries, change exits, or change leverage rules.

## Run Focused Tests

```bash
make test-btcusdc-v220
```

## Refresh Execution, Readiness, And Launch Evidence

```bash
make btcusdc-v205-execution-validation
make btcusdc-v204-real-money-readiness-gate
make btcusdc-v206-real-money-launch-preflight
PYTHONPATH=src python -m lob_microprice_lab.cli real-trade-btcusdc \
  --out runs/research_v207_real_trade_cli_preflight \
  --arm-real-money-token I_UNDERSTAND_THIS_USES_REAL_MONEY
```

The CLI returns exit code `2` when launch is blocked.

## Required Recent Execution Evidence

Real-money launch remains blocked unless:

- V205 has at least 30 clean execution fills
- every fill is marked `filled`
- execution and signal provenance are clean
- p95 slippage is within the configured cap
- kill-switch evidence exists
- repository secret scan is clean
- latest execution evidence is recent enough for the configured max age
- V204 and V206 both carry and enforce the recent execution evidence check

## Outputs

```text
reports/RESEARCH_V205_BTCUSDC_EXECUTION_VALIDATION.md
reports/RESEARCH_V220_BTCUSDC_RECENT_EXECUTION_EVIDENCE_LOCK.md
runs/research_v204_real_money_execution_validation/execution_validation_summary.json
runs/research_v204_real_money_readiness_gate/v204_real_money_readiness_summary.json
runs/research_v206_real_money_launch_preflight/v206_real_money_launch_preflight_summary.json
runs/research_v207_real_trade_cli_preflight/real_money_launch_preflight_summary.json
```

The `runs/` outputs are local generated evidence and should not be committed.
