# Research V154 Commands

V154 tests a fixed rescue funding boost plus premium stress stabilizer on top of the promoted V153 BTCUSDC account path.

The fixed hypothesis has two parts:

- Boost calm-funding rescue longs:
  - Segment: `rescue_long`
  - Feature: `funding_abs_z_30d`
  - Threshold: selector-period `q0.60`
  - Condition: `funding_abs_z_30d <= threshold`
  - Sizing: multiply existing V153 trade return by `1.10`
- Add a small stabilizer to weak base-long premium crowd-follow:
  - Segment: `base_long`
  - Feature: `premium_crowd_follow_120d`
  - Threshold: selector-period `q0.10`
  - Condition: `premium_crowd_follow_120d <= threshold`
  - Sizing: multiply existing V153 trade return by `0.90`
- New trades: none

Run the research script:

```bash
make btcusdc-v154-rescue-funding-stabilizer
```

Run the focused tests:

```bash
make test-btcusdc-v154
```

Run the repository verification checks:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

Primary outputs:

- `reports/RESEARCH_V154_BTCUSDC_RESCUE_FUNDING_STABILIZER.md`
- `runs/research_v154_rescue_funding_stabilizer/v154_rescue_funding_stabilizer_summary.json`
- `runs/research_v154_rescue_funding_stabilizer/v154_rescue_funding_stabilizer_candidate.csv`
- `runs/research_v154_rescue_funding_stabilizer/v154_selected_account_path.csv`
- `runs/research_v154_rescue_funding_stabilizer/v154_monthly_account_return.csv`
- `runs/research_v154_rescue_funding_stabilizer/v154_rescue_funding_context_metrics.csv`

The `runs/` files are local generated artifacts and are not committed.

This is a research audit, not a live trading guarantee.
