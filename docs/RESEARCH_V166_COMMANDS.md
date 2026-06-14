# Research V166 Commands

V166 converts V165 monthly cost fragility into maker/taker execution budgets. It estimates how much taker-style extra cost each month can tolerate before breakeven headroom is exhausted.

## Focused Test

```bash
make test-btcusdc-v166
```

## Run V166 Audit

```bash
make btcusdc-v166-execution-budget-audit
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

```text
runs/research_v166_execution_budget_audit/v166_execution_budget_taker4bps.csv
runs/research_v166_execution_budget_audit/v166_execution_budget_taker2bps.csv
runs/research_v166_execution_budget_audit/v166_execution_budget_audit_summary.json
reports/RESEARCH_V166_BTCUSDC_EXECUTION_BUDGET_AUDIT.md
```

## Research Notes

- Base: V165 monthly cost fragility table.
- Primary taker extra cost assumption: 4 bps.
- Secondary taker extra cost assumption: 2 bps.
- `max_taker_share = min(1, breakeven_extra_cost_bps / taker_extra_cost_bps)`.
- `required_maker_share = 1 - max_taker_share`.
- The audit does not add trades, change sides, or promote the system for live trading.
- This is a research audit, not a live trading guarantee.
