# Research V157 Commands

V157 audits whether a single market-condition overlay can safely improve V156 after the base-long premium stepup. It is a promotion audit: passing candidates should be implemented in a separate fixed model rather than traded directly from the broad scan.

## Focused Test

```bash
make test-btcusdc-v157
```

## Run V157

```bash
make btcusdc-v157-market-condition-post-stepup-audit
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

```text
runs/research_v157_market_condition_post_stepup_audit/v157_fast_candidate_scan.csv
runs/research_v157_market_condition_post_stepup_audit/v157_return_eligible_candidates.csv
runs/research_v157_market_condition_post_stepup_audit/v157_rejection_summary.csv
runs/research_v157_market_condition_post_stepup_audit/v157_market_condition_post_stepup_summary.json
reports/RESEARCH_V157_BTCUSDC_MARKET_CONDITION_POST_STEPUP_AUDIT.md
```

## Research Notes

- Base: V156 selected account path.
- Candidate features include trend, range, funding, premium, probability, and intraday activity fields.
- Thresholds use selector-period quantiles only.
- Holdout is used only for validation.
- A candidate must improve full/selector/holdout return and must not worsen drawdown, worst month, or positive-month coverage.
- This is a research audit, not a live trading guarantee.
