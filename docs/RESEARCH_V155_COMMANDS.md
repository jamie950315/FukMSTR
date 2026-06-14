# Research V155 Commands

V155 tests a fixed base-long calm-premium sizing expansion on top of the promoted V154 BTCUSDC account path.

The fixed hypothesis:

- Segment: `base_long`
- Feature: `premium_abs_bps`
- Threshold: selector-period `q0.60`
- Condition: `premium_abs_bps <= threshold`
- Sizing: multiply existing V154 trade return by `1.075`
- New trades: none

Run the research script:

```bash
make btcusdc-v155-base-long-premium-expansion
```

Run the focused tests:

```bash
make test-btcusdc-v155
```

Run the repository verification checks:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

Primary outputs:

- `reports/RESEARCH_V155_BTCUSDC_BASE_LONG_PREMIUM_EXPANSION.md`
- `runs/research_v155_base_long_premium_expansion/v155_base_long_premium_expansion_summary.json`
- `runs/research_v155_base_long_premium_expansion/v155_base_long_premium_expansion_candidate.csv`
- `runs/research_v155_base_long_premium_expansion/v155_selected_account_path.csv`
- `runs/research_v155_base_long_premium_expansion/v155_monthly_account_return.csv`
- `runs/research_v155_base_long_premium_expansion/v155_base_long_premium_context_metrics.csv`

The `runs/` files are local generated artifacts and are not committed.

This is a research audit, not a live trading guarantee.
