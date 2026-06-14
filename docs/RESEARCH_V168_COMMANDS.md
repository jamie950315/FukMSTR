# Research V168 Commands

V168 converts the V166 maker/taker execution budget into a monthly execution readiness gate. It turns required maker share into concrete live-gate actions such as maker-only required, maker-priority required, mixed execution allowed, or normal cost monitoring.

## Focused Test

```bash
make test-btcusdc-v168
```

## Run V168 Audit

```bash
make btcusdc-v168-execution-readiness-gate
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

```text
runs/research_v168_execution_readiness_gate/v168_execution_readiness_gate.csv
runs/research_v168_execution_readiness_gate/v168_execution_readiness_summary.csv
runs/research_v168_execution_readiness_gate/v168_execution_readiness_gate_summary.json
reports/RESEARCH_V168_BTCUSDC_EXECUTION_READINESS_GATE.md
```

## Research Notes

- Base: V166 execution budget at 4 bps modeled taker extra cost.
- `required_maker_share >= 0.80`: maker-only required.
- `0.50 <= required_maker_share < 0.80`: maker-priority required.
- `0 < required_maker_share < 0.50`: mixed execution allowed, with taker share capped.
- `required_maker_share == 0`: normal cost monitoring.
- The gate does not add trades, change sides, change thresholds, or promote live trading.
- This is a research execution gate, not a live trading guarantee.
