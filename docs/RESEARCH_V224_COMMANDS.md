# Research V224 Commands

V224 hardens the no-overfitting forward-monitoring chain with a fixed forward-freeze manifest. V196 now requires a matching manifest for the freeze timestamp, and V204/V206/CLI require that manifest before any real-money launch path can pass.

V224 does not place live orders, tune thresholds, change entries, change exits, or change leverage rules.

## Run Focused Tests

```bash
make test-btcusdc-v224
```

## Refresh Forward, Readiness, And Launch Evidence

```bash
make btcusdc-v196-forward-monitoring-gate
make btcusdc-v205-execution-validation
make btcusdc-v204-real-money-readiness-gate
make btcusdc-v206-real-money-launch-preflight
PYTHONPATH=src python -m lob_microprice_lab.cli real-trade-btcusdc \
  --out runs/research_v207_real_trade_cli_preflight \
  --arm-real-money-token I_UNDERSTAND_THIS_USES_REAL_MONEY
```

The CLI returns exit code `2` when launch is blocked.

## Required Forward-Freeze Provenance

Real-money launch remains blocked unless:

- V196 records `configs/btcusdc_v224_forward_freeze_manifest.json`
- the manifest freeze timestamp matches V196's freeze timestamp
- the manifest keeps historical optimization disabled
- the manifest requires forward-only rows after the freeze timestamp
- V204 carries the manifest path and SHA256 hash
- V206 and the CLI recompute the current manifest hash and match V204

## Outputs

```text
configs/btcusdc_v224_forward_freeze_manifest.json
reports/RESEARCH_V224_BTCUSDC_FORWARD_FREEZE_MANIFEST_LOCK.md
runs/research_v196_forward_monitoring_gate/v196_forward_monitoring_gate_summary.json
runs/research_v204_real_money_readiness_gate/v204_real_money_readiness_summary.json
runs/research_v206_real_money_launch_preflight/v206_real_money_launch_preflight_summary.json
runs/research_v207_real_trade_cli_preflight/real_money_launch_preflight_summary.json
```

The `runs/` outputs are local generated evidence and should not be committed.
