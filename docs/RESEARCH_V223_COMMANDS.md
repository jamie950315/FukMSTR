# Research V223 Commands

V223 hardens the real-money readiness chain with a fixed strategy manifest lock. V204 now records the promoted strategy manifest path and SHA256 hash, and V206 plus the `real-trade-btcusdc` CLI recompute that hash before any real-money launch path can pass.

The promoted manifest currently identifies V193 as the official BTCUSDC online/paper iteration for monitoring and historical replay.

V223 does not place live orders, tune thresholds, change entries, change exits, or change leverage rules.

## Run Focused Tests

```bash
make test-btcusdc-v223
```

## Refresh Readiness And Launch Evidence

```bash
make btcusdc-v205-execution-validation
make btcusdc-v204-real-money-readiness-gate
make btcusdc-v206-real-money-launch-preflight
PYTHONPATH=src python -m lob_microprice_lab.cli real-trade-btcusdc \
  --out runs/research_v207_real_trade_cli_preflight \
  --arm-real-money-token I_UNDERSTAND_THIS_USES_REAL_MONEY
```

The CLI returns exit code `2` when launch is blocked.

## Required Strategy Manifest Provenance

Real-money launch remains blocked unless:

- V204 records `configs/btcusdc_v223_promoted_strategy_manifest.json`
- the manifest identifies `official_online_iteration=V193`
- V204 records a non-missing strategy manifest SHA256 hash
- V206 recomputes the current manifest hash and matches V204
- the CLI recomputes the current manifest hash and matches V204
- runtime source files remain clean

## Outputs

```text
configs/btcusdc_v223_promoted_strategy_manifest.json
reports/RESEARCH_V223_BTCUSDC_STRATEGY_MANIFEST_LOCK.md
runs/research_v204_real_money_readiness_gate/v204_real_money_readiness_summary.json
runs/research_v206_real_money_launch_preflight/v206_real_money_launch_preflight_summary.json
runs/research_v207_real_trade_cli_preflight/real_money_launch_preflight_summary.json
```

The `runs/` outputs are local generated evidence and should not be committed.
