# V207 Real-Trade CLI Preflight Commands

V207 adds a real-money CLI entrypoint that only runs launch preflight checks.
It does not place live orders, tune thresholds, change entries, change exits, or change leverage rules.

## Run

```bash
make btcusdc-v207-real-trade-cli-preflight
```

The target accepts either:

- exit code `0` when every preflight check passes;
- exit code `2` when real-money launch is blocked by safety gates.

Any other exit code is treated as a failure.

## Direct CLI

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli real-trade-btcusdc \
  --out runs/research_v207_real_trade_cli_preflight \
  --arm-real-money-token I_UNDERSTAND_THIS_USES_REAL_MONEY
```

Current expected result is blocked because V204 is not `real_money_ready`.

The CLI also re-checks the V223 fixed strategy manifest hash recorded by V204.

## Focused Test

```bash
make test-btcusdc-v207
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

- `runs/research_v207_real_trade_cli_preflight/real_money_launch_preflight_summary.json`

The `runs/` output is local generated evidence and should not be committed.
