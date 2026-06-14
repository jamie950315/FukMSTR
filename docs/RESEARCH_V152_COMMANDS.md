# Research V152 Commands

V152 tests a strict 60-minute short trend activity sizing overlay on top of the promoted V151 BTCUSDC account path.

The fixed hypothesis is:

- Feature: `trend_abs_60_bps`
- Threshold: selector-period `q0.85`
- Condition: `trend_abs_60_bps >= threshold`
- Sizing: multiply existing V151 trade return by `1.05`
- New trades: none

Run the research script:

```bash
make btcusdc-v152-short-trend-activity-overlay
```

Run the focused tests:

```bash
make test-btcusdc-v152
```

Run the repository verification checks:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

Primary outputs:

- `reports/RESEARCH_V152_BTCUSDC_SHORT_TREND_ACTIVITY_OVERLAY.md`
- `runs/research_v152_short_trend_activity_overlay/v152_short_trend_activity_summary.json`
- `runs/research_v152_short_trend_activity_overlay/v152_short_trend_activity_candidates.csv`
- `runs/research_v152_short_trend_activity_overlay/v152_selected_account_path.csv`
- `runs/research_v152_short_trend_activity_overlay/v152_activity_context_metrics.csv`

The `runs/` files are local generated artifacts and are not committed.

This is a research audit, not a live trading guarantee.
