# Research V170 Commands

V170 evaluates execution-aware risk-control policies on top of the V162 selected account path and the V168 monthly execution readiness gate. It checks whether maker-only or maker-priority months should be scaled down or skipped without adding trades, changing side, or changing the core strategy threshold.

## Focused Test

```bash
make test-btcusdc-v170
```

## Run V170 Audit

```bash
make btcusdc-v170-execution-aware-risk-control
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

```text
runs/research_v170_execution_aware_risk_control/v170_policy_comparison.csv
runs/research_v170_execution_aware_risk_control/v170_selected_monthly_path.csv
runs/research_v170_execution_aware_risk_control/v170_selected_mode_profile.csv
runs/research_v170_execution_aware_risk_control/v170_execution_aware_risk_control_summary.json
runs/research_v170_execution_aware_risk_control/*_path.csv
reports/RESEARCH_V170_BTCUSDC_EXECUTION_AWARE_RISK_CONTROL.md
```

## Research Notes

- Base trades: V162 selected account path.
- Execution mode source: V168 monthly execution readiness gate.
- Policy candidates only scale or skip existing trades in fragile execution months.
- V170 does not add trades, change side, change threshold, or promote live trading.
- This is a research execution-risk audit, not a live trading guarantee.
