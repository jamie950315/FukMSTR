# V206 Real-Money Launch Preflight Commands

V206 adds a final launch preflight for any future real-money path.
It does not place live orders, tune thresholds, change entries, change exits, or change leverage rules.

## Default Run

```bash
make btcusdc-v206-real-money-launch-preflight
```

The default run does not pass the explicit real-money arm token, so it should block launch.

## Explicit Real-Money Arm

Only use this after V204 reports `real_money_ready`:

```bash
PYTHONPATH=src python scripts/run_btcusdc_v206_real_money_launch_preflight.py \
  --arm-real-money-token I_UNDERSTAND_THIS_USES_REAL_MONEY
```

The preflight still does not place orders. It only confirms whether a future live executor may be launched.

## Required Gates

V206 allows real-money launch only when all checks pass:

- V204 readiness gate reports `real_money_ready`
- V204 summary includes V212 forward freshness evidence
- V212 freshness evidence reports current forward data and enough passing forward trades
- `promote_to_real_money` is `true`
- no V204 failed checks remain
- V204 summary includes the V223 fixed strategy manifest path and hash
- the current strategy manifest hash still matches the V204 summary
- V204 summary includes the V224 forward-freeze manifest path and hash
- the current forward-freeze manifest hash still matches the V204 summary
- the explicit arm token is provided
- runtime source files are clean

Runtime source includes:

- `configs/`
- `src/`
- `scripts/`
- `tests/`
- `Makefile`
- `pyproject.toml`
- `requirements.txt`

## Focused Test

```bash
make test-btcusdc-v206
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

- `reports/RESEARCH_V206_BTCUSDC_REAL_MONEY_LAUNCH_PREFLIGHT.md`
- `runs/research_v206_real_money_launch_preflight/v206_real_money_launch_preflight_summary.json`

The `runs/` output is local generated evidence and should not be committed.
