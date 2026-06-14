# Research V165 Commands

V165 audits the monthly cost fragility behind the V164 extra-cost warning. It identifies which months lack enough breakeven headroom when extra execution cost is added to the V162 selected account path.

## Focused Test

```bash
make test-btcusdc-v165
```

## Run V165 Audit

```bash
make btcusdc-v165-cost-fragility-audit
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

```text
runs/research_v165_cost_fragility_audit/v165_monthly_cost_fragility.csv
runs/research_v165_cost_fragility_audit/v165_negative_months_after_2bps.csv
runs/research_v165_cost_fragility_audit/v165_negative_months_after_4bps.csv
runs/research_v165_cost_fragility_audit/v165_cost_fragility_audit_summary.json
reports/RESEARCH_V165_BTCUSDC_COST_FRAGILITY_AUDIT.md
```

## Research Notes

- Base: V162 selected account path.
- Monthly cost load is `sum(account_leverage * position_weight / 100)`.
- Monthly breakeven extra cost is `monthly_return_pct / monthly_cost_load_per_1bps_pct`.
- Months below the required 4 bps headroom are tagged as fragile.
- The audit does not add trades, change sides, or promote the system for live trading.
- This is a research audit, not a live trading guarantee.
