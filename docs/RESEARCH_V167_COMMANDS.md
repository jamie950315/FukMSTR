# Research V167 Commands

V167 classifies the V143-V166 market-condition research into allowed roles. It answers whether trend/emotion data should be used as entry logic, sizing context, monitoring context, or execution risk control.

## Focused Test

```bash
make test-btcusdc-v167
```

## Run V167 Audit

```bash
make btcusdc-v167-market-condition-role-audit
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

```text
runs/research_v167_market_condition_role_audit/v167_market_condition_role_catalog.csv
runs/research_v167_market_condition_role_audit/v167_market_condition_role_summary.csv
runs/research_v167_market_condition_role_audit/v167_market_condition_role_audit_summary.json
reports/RESEARCH_V167_BTCUSDC_MARKET_CONDITION_ROLE_AUDIT.md
```

## Research Notes

- Base: V143-V166 research reports.
- The audit does not add trades, change sides, change thresholds, or promote live trading.
- Market condition data is not allowed as a standalone entry or side signal.
- Passed market condition overlays are classified as sizing or risk-governor context only.
- Short-history derivatives positioning data remains monitor-only.
- Slow macro sentiment such as Fear & Greed remains macro context only.
- This is a research audit, not a live trading guarantee.
