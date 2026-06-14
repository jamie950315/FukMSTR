# Research V177 Commands

V177 audits whether V176's combined state overlay is stable enough to treat as a stronger research candidate.

The audit uses the V176 selected BTCUSDC account path and does not add trades, change side, change signal thresholds, or promote live trading.

## Focused Checks

```bash
make test-btcusdc-v177
make btcusdc-v177-v176-stability-audit
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Inputs

```text
runs/research_v176_combined_state_overlay/v176_selected_account_path.csv
```

If the V176 selected account path is missing, the V177 script rebuilds it through the V176 runner.

## Outputs

```text
runs/research_v177_v176_stability_audit/v177_period_stability.csv
runs/research_v177_v176_stability_audit/v177_monthly_stability.csv
runs/research_v177_v176_stability_audit/v177_action_contribution_profile.csv
runs/research_v177_v176_stability_audit/v177_v176_stability_audit_summary.json
reports/RESEARCH_V177_BTCUSDC_V176_STABILITY_AUDIT.md
```

## Audit Scope

- Period split: selector before 2026-01-01 UTC; holdout from 2026-01-01 UTC onward.
- Monthly stability: compare V176 return against V162 baseline by month.
- Action contribution: compare boosted, throttled, and unchanged trades.
- Small sample check: boosted trade count must be at least 20 to pass.
- Concentration check: no single month should contain more than 40% of boosted trades.

This remains a research audit and is not evidence of future live trading profit.
