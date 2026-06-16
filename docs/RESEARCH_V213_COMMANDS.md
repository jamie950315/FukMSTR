# Research V213 Commands

V213 hardens the real-money launch preflight path. A `real_money_ready` V204 summary is no longer enough by itself; the summary must also contain V212 forward-freshness evidence showing current forward data and enough passing forward trades.

V213 does not place live orders, tune thresholds, change entries, change exits, or change leverage rules.

## Run Focused Tests

```bash
make test-btcusdc-v213
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
- V212 freshness evidence reports current forward data and enough passing forward trades
- the explicit arm token is provided
- runtime source files are clean

## Outputs

```text
reports/RESEARCH_V213_BTCUSDC_LAUNCH_PREFLIGHT_FRESHNESS_LOCK.md
runs/research_v206_real_money_launch_preflight/v206_real_money_launch_preflight_summary.json
runs/research_v207_real_trade_cli_preflight/real_money_launch_preflight_summary.json
```

The `runs/` outputs are local generated evidence and should not be committed.
