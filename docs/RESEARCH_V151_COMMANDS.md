# Research V151 Commands

V151 tests a 24-hour range-alignment sizing overlay on top of the promoted V150 BTCUSDC account path.

Run the research script:

```bash
make btcusdc-v151-range-alignment-overlay
```

Run the focused tests:

```bash
make test-btcusdc-v151
```

Run the repository verification checks:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

Primary outputs:

- `reports/RESEARCH_V151_BTCUSDC_RANGE_ALIGNMENT_OVERLAY.md`
- `runs/research_v151_range_alignment_overlay/v151_range_alignment_summary.json`
- `runs/research_v151_range_alignment_overlay/v151_range_alignment_candidates.csv`
- `runs/research_v151_range_alignment_overlay/v151_selected_account_path.csv`

The `runs/` files are local generated artifacts and are not committed.
