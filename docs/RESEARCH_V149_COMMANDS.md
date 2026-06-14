# Research V149 Commands

V149 tests a confidence-persistence sizing overlay on top of the promoted V148 BTCUSDC account path.

Run the research script:

```bash
make btcusdc-v149-confidence-persistence-overlay
```

Run the focused tests:

```bash
make test-btcusdc-v149
```

Run the repository verification checks:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

Primary outputs:

- `reports/RESEARCH_V149_BTCUSDC_CONFIDENCE_PERSISTENCE_OVERLAY.md`
- `runs/research_v149_confidence_persistence_overlay/v149_confidence_persistence_summary.json`
- `runs/research_v149_confidence_persistence_overlay/v149_confidence_persistence_candidates.csv`
- `runs/research_v149_confidence_persistence_overlay/v149_selected_account_path.csv`

The `runs/` files are local generated artifacts and are not committed.
