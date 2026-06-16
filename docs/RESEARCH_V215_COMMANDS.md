# Research V215 Commands

V215 hardens the real-money launch preflight path. A `real_money_ready` V204 summary must include both V212 forward-freshness evidence and V214 public-data availability evidence before V206 or the `real-trade-btcusdc` CLI can pass.

V215 does not place live orders, tune thresholds, change entries, change exits, or change leverage rules.

## Run Focused Tests

```bash
make test-btcusdc-v215
```

## Run Real-Money Preflight Checks

```bash
make btcusdc-v206-real-money-launch-preflight
PYTHONPATH=src python -m lob_microprice_lab.cli real-trade-btcusdc \
  --out runs/research_v207_real_trade_cli_preflight \
  --arm-real-money-token I_UNDERSTAND_THIS_USES_REAL_MONEY
```

The CLI returns exit code `2` when launch is blocked.

## Required Gates

Real-money launch remains blocked unless all checks pass:

- V204 readiness gate reports `real_money_ready`
- V204 summary includes V212 forward-freshness evidence
- V204 summary includes V214 public-data availability evidence
- the explicit arm token is provided
- runtime source files are clean

## Outputs

```text
reports/RESEARCH_V215_BTCUSDC_LAUNCH_PUBLIC_DATA_LOCK.md
runs/research_v206_real_money_launch_preflight/v206_real_money_launch_preflight_summary.json
runs/research_v207_real_trade_cli_preflight/real_money_launch_preflight_summary.json
```

The `runs/` outputs are local generated evidence and should not be committed.
