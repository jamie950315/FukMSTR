# Research V169 Commands

V169 joins V162 selected trades to the V168 monthly execution readiness gate and profiles fragile execution months at trade level. The goal is to understand whether maker-only or maker-priority months are different by side mix, leg mix, leverage, position weight, confidence, and realized return.

## Focused Test

```bash
make test-btcusdc-v169
```

## Run V169 Audit

```bash
make btcusdc-v169-fragile-execution-profile
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

```text
runs/research_v169_fragile_execution_profile/v169_trade_execution_profile.csv
runs/research_v169_fragile_execution_profile/v169_fragile_vs_normal_profile.csv
runs/research_v169_fragile_execution_profile/v169_execution_mode_profile.csv
runs/research_v169_fragile_execution_profile/v169_side_leg_profile.csv
runs/research_v169_fragile_execution_profile/v169_monthly_profile.csv
runs/research_v169_fragile_execution_profile/v169_fragile_execution_profile_summary.json
reports/RESEARCH_V169_BTCUSDC_FRAGILE_EXECUTION_PROFILE.md
```

## Research Notes

- Base trades: V162 selected account path.
- Execution gate: V168 monthly execution readiness gate.
- Fragile execution group: maker-only, maker-priority, or no-trade-unless-cost-improves months.
- This audit does not add trades, change sides, change thresholds, or promote live trading.
- This is a research execution profile, not a live trading guarantee.
