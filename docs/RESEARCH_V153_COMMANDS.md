# Research V153 Commands

V153 tests a fixed premium-basis sizing overlay on top of the promoted V152 BTCUSDC account path.

The fixed hypothesis has two parts:

- Boost calm long premium:
  - Segment: `long`
  - Feature: `premium_abs_bps`
  - Threshold: selector-period `q0.20`
  - Condition: `premium_abs_bps <= threshold`
  - Sizing: multiply existing V152 trade return by `1.15`
- Throttle weak base-long premium crowd-follow:
  - Segment: `base_long`
  - Feature: `premium_crowd_follow_120d`
  - Threshold: selector-period `q0.10`
  - Condition: `premium_crowd_follow_120d <= threshold`
  - Sizing: multiply existing V152 trade return by `0.70`
- New trades: none

Run the research script:

```bash
make btcusdc-v153-premium-balance-overlay
```

Run the focused tests:

```bash
make test-btcusdc-v153
```

Run the repository verification checks:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

Primary outputs:

- `reports/RESEARCH_V153_BTCUSDC_PREMIUM_BALANCE_OVERLAY.md`
- `runs/research_v153_premium_balance_overlay/v153_premium_balance_summary.json`
- `runs/research_v153_premium_balance_overlay/v153_premium_balance_candidate.csv`
- `runs/research_v153_premium_balance_overlay/v153_selected_account_path.csv`
- `runs/research_v153_premium_balance_overlay/v153_monthly_account_return.csv`
- `runs/research_v153_premium_balance_overlay/v153_premium_balance_context_metrics.csv`

The `runs/` files are local generated artifacts and are not committed.

This is a research audit, not a live trading guarantee.
