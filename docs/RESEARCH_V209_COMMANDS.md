# V209 Execution Provenance Gate Commands

V209 tightens V205 execution validation by requiring order-level provenance for fill evidence.
It does not place live orders, tune thresholds, change entries, change exits, or change leverage rules.

## Run

```bash
make btcusdc-v209-execution-provenance-gate
```

## Focused Test

```bash
make test-btcusdc-v209
```

## Related Gate Check

```bash
make btcusdc-v205-execution-validation
make btcusdc-v204-real-money-readiness-gate
```

V205 now requires these fill-audit provenance fields:

- `venue`
- `execution_mode`
- `evidence_source`
- `capture_id`
- `order_id`
- `client_order_id`
- `exchange_timestamp`

Allowed execution modes are:

- `paper_shadow_live`
- `exchange_testnet`
- `exchange_live_min_size`

Synthetic, backtest, manual, unknown, or blank evidence sources are not accepted.

For `paper_shadow_live` fills, V209 inherits V205's V222 requirement: the fill audit must be backed by a matching V210 capture summary.

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

- `runs/research_v209_execution_provenance_gate/v209_execution_provenance_gate_summary.json`
- `reports/RESEARCH_V209_BTCUSDC_EXECUTION_PROVENANCE_GATE.md`

The `runs/` output is local generated evidence and should not be committed.
