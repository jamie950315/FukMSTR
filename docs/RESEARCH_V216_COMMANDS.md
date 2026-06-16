# Research V216 Commands

V216 hardens the V204 real-money readiness gate. A legacy or manually edited execution summary is no longer enough for V204 unless it includes V205/V209-compatible execution and signal provenance checks.

V216 does not place live orders, tune thresholds, change entries, change exits, or change leverage rules.

## Run Focused Tests

```bash
make test-btcusdc-v216
```

## Refresh Readiness Evidence

```bash
make btcusdc-v205-execution-validation
make btcusdc-v209-execution-provenance-gate
make btcusdc-v204-real-money-readiness-gate
make btcusdc-v206-real-money-launch-preflight
PYTHONPATH=src python -m lob_microprice_lab.cli real-trade-btcusdc \
  --out runs/research_v207_real_trade_cli_preflight \
  --arm-real-money-token I_UNDERSTAND_THIS_USES_REAL_MONEY
```

The CLI returns exit code `2` when launch is blocked.

## Required Execution Evidence

V204 now requires these V205/V209 execution checks before it can report `real_money_ready`:

- fill evidence is available
- every fill status is `filled`
- order-level execution provenance is clean
- signal and market provenance are clean
- p95 slippage is within budget
- kill switch evidence exists
- no obvious tracked repo secrets are detected

## Outputs

```text
reports/RESEARCH_V216_BTCUSDC_READINESS_EXECUTION_PROVENANCE_LOCK.md
runs/research_v204_real_money_readiness_gate/v204_real_money_readiness_summary.json
runs/research_v206_real_money_launch_preflight/v206_real_money_launch_preflight_summary.json
runs/research_v207_real_trade_cli_preflight/real_money_launch_preflight_summary.json
```

The `runs/` outputs are local generated evidence and should not be committed.
