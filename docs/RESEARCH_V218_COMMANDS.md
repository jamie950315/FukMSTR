# Research V218 Commands

V218 hardens the final real-money launch evidence chain. A V204 readiness summary must prove it was generated from the same git commit that is launching V206 or the `real-trade-btcusdc` CLI, and it must prove runtime source files were clean when V204 generated the summary.

V218 does not place live orders, tune thresholds, change entries, change exits, or change leverage rules.

## Run Focused Tests

```bash
make test-btcusdc-v218
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

## Required Source Provenance

Real-money launch remains blocked unless:

- V204 summary includes `requires_readiness_source_provenance`
- V204 summary records the git commit that generated it
- V204 summary records clean runtime source at generation time
- V206/CLI current git commit matches the V204 summary commit
- V206/CLI runtime source files are still clean at launch time

## Outputs

```text
reports/RESEARCH_V218_BTCUSDC_READINESS_SOURCE_PROVENANCE_LOCK.md
runs/research_v204_real_money_readiness_gate/v204_real_money_readiness_summary.json
runs/research_v206_real_money_launch_preflight/v206_real_money_launch_preflight_summary.json
runs/research_v207_real_trade_cli_preflight/real_money_launch_preflight_summary.json
```

The `runs/` outputs are local generated evidence and should not be committed.
