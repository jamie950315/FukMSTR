# Research V150 Commands

V150 tests a long-horizon funding-persistence sizing overlay on top of the promoted V149 BTCUSDC account path.

Run the research script:

```bash
make btcusdc-v150-funding-persistence-overlay
```

Run the focused tests:

```bash
make test-btcusdc-v150
```

Run the repository verification checks:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

Primary outputs:

- `reports/RESEARCH_V150_BTCUSDC_FUNDING_PERSISTENCE_OVERLAY.md`
- `runs/research_v150_funding_persistence_overlay/v150_funding_persistence_summary.json`
- `runs/research_v150_funding_persistence_overlay/v150_funding_persistence_candidates.csv`
- `runs/research_v150_funding_persistence_overlay/v150_selected_account_path.csv`

The `runs/` files are local generated artifacts and are not committed.
