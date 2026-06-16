# Research V219 Commands

V219 hardens the final real-money launch evidence chain. A V204 readiness summary must record SHA256 hashes for the evidence files it consumed, and V206 or the `real-trade-btcusdc` CLI must verify those hashes still match before launch preflight can pass.

V219 does not place live orders, tune thresholds, change entries, change exits, or change leverage rules.

## Run Focused Tests

```bash
make test-btcusdc-v219
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

## Required Input Hash Evidence

Real-money launch remains blocked unless:

- V204 summary includes `requires_readiness_input_hashes`
- V204 summary records every consumed evidence input path
- V204 summary records a non-missing SHA256 hash for each input
- V206/CLI recomputes every input hash and matches V204's recorded hashes
- runtime source files are still clean at launch time

## Outputs

```text
reports/RESEARCH_V219_BTCUSDC_READINESS_INPUT_HASH_LOCK.md
runs/research_v204_real_money_readiness_gate/v204_real_money_readiness_summary.json
runs/research_v206_real_money_launch_preflight/v206_real_money_launch_preflight_summary.json
runs/research_v207_real_trade_cli_preflight/real_money_launch_preflight_summary.json
```

The `runs/` outputs are local generated evidence and should not be committed.
