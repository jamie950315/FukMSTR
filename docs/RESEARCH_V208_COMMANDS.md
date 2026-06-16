# V208 Kill-Switch Self-Test Commands

V208 adds a local kill-switch self-test evidence generator for V205.
It does not place live orders, tune thresholds, change entries, change exits, or change leverage rules.

## Run

```bash
make btcusdc-v208-kill-switch-self-test
```

## Focused Test

```bash
make test-btcusdc-v208
```

## Follow-Up Gate Check

```bash
make btcusdc-v205-execution-validation
```

After V208 evidence exists locally, V205 should no longer fail on `kill_switch_tested`.
It can still block real-money use if fill and slippage evidence is missing or failed.

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

- `runs/research_v208_kill_switch_self_test/v208_kill_switch_self_test_summary.json`
- `runs/research_v205_execution_validation/kill_switch_events.csv`
- `reports/RESEARCH_V208_BTCUSDC_KILL_SWITCH_SELF_TEST.md`

The `runs/` outputs are local generated evidence and should not be committed.
