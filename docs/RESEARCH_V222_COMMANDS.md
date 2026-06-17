# Research V222 Commands

V222 hardens the paper-shadow execution evidence chain. V205 now requires a matching V210 capture summary when validating `paper_shadow_live` fills, and V204/V206/CLI require that check before any real-money launch path can pass.

V222 does not place live orders, tune thresholds, change entries, change exits, or change leverage rules.

## Run Focused Tests

```bash
make test-btcusdc-v222
```

## Refresh Capture, Execution, Readiness, And Launch Evidence

```bash
make btcusdc-v210-paper-shadow-fill-capture SIGNAL_CSV=/path/to/signals.csv TICKS=60 CAPTURE_ID=paper-shadow-YYYYMMDD
make btcusdc-v208-kill-switch-self-test
make btcusdc-v205-execution-validation
make btcusdc-v204-real-money-readiness-gate
make btcusdc-v206-real-money-launch-preflight
PYTHONPATH=src python -m lob_microprice_lab.cli real-trade-btcusdc \
  --out runs/research_v207_real_trade_cli_preflight \
  --arm-real-money-token I_UNDERSTAND_THIS_USES_REAL_MONEY
```

The CLI returns exit code `2` when launch is blocked.

## Required Paper-Shadow Capture Provenance

For `paper_shadow_live` fills, real-money launch remains blocked unless:

- V210 capture summary exists
- V210 status is `paper_shadow_fill_capture_ready_for_v205`
- V210 and the fill audit agree on fill count
- V210 and the fill audit agree on capture ID
- V210 and the fill audit agree on evidence source
- V210 config and decision both show `places_live_orders=False`
- V204 and V206 both carry and enforce the V222 check

## Outputs

```text
reports/RESEARCH_V222_BTCUSDC_PAPER_SHADOW_CAPTURE_PROVENANCE_LOCK.md
runs/research_v210_paper_shadow_fill_capture/v210_paper_shadow_fill_capture_summary.json
runs/research_v204_real_money_execution_validation/execution_validation_summary.json
runs/research_v204_real_money_readiness_gate/v204_real_money_readiness_summary.json
runs/research_v206_real_money_launch_preflight/v206_real_money_launch_preflight_summary.json
runs/research_v207_real_trade_cli_preflight/real_money_launch_preflight_summary.json
```

The `runs/` outputs are local generated evidence and should not be committed.
