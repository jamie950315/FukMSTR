# Research V221 Commands

V221 hardens source provenance without making report-only commits look like runtime source changes. V204 records a hash of tracked runtime source files, and V206/CLI recompute that hash before launch preflight. A later report-only commit can be accepted only when the recorded code commit is an ancestor of the current commit and the runtime source hash still matches.

V221 does not place live orders, tune thresholds, change entries, change exits, or change leverage rules.

## Run Focused Tests

```bash
make test-btcusdc-v221
```

## Refresh Readiness And Launch Evidence

```bash
make btcusdc-v204-real-money-readiness-gate
make btcusdc-v206-real-money-launch-preflight
PYTHONPATH=src python -m lob_microprice_lab.cli real-trade-btcusdc \
  --out runs/research_v207_real_trade_cli_preflight \
  --arm-real-money-token I_UNDERSTAND_THIS_USES_REAL_MONEY
```

The CLI returns exit code `2` when launch is blocked.

## Required Runtime Source Evidence

Real-money launch remains blocked unless:

- V204 records `readiness_runtime_source_hash`
- V204 reports `readiness_runtime_source_hash_clean=True`
- V206/CLI recomputes the current runtime source hash
- the current runtime source hash matches the V204 recorded hash
- the recorded V204 source commit is the current commit or an ancestor of the current commit
- runtime source files are not dirty at launch time

## Outputs

```text
reports/RESEARCH_V221_BTCUSDC_RUNTIME_SOURCE_HASH_LOCK.md
runs/research_v204_real_money_readiness_gate/v204_real_money_readiness_summary.json
runs/research_v206_real_money_launch_preflight/v206_real_money_launch_preflight_summary.json
runs/research_v207_real_trade_cli_preflight/real_money_launch_preflight_summary.json
```

The `runs/` outputs are local generated evidence and should not be committed.
