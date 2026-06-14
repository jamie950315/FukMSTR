# Research V173 Commands

V173 tests timestamp-side exposure caps on top of the V162 selected account path. It was motivated by V171 and V172: the max-drawdown cluster included simultaneous same-side source stacking, while prior rescue-count guards did not help.

## Focused Test

```bash
make test-btcusdc-v173
```

## Run V173 Audit

```bash
make btcusdc-v173-timestamp-side-exposure-cap
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

```text
runs/research_v173_timestamp_side_exposure_cap/v173_policy_comparison.csv
runs/research_v173_timestamp_side_exposure_cap/v173_selected_capped_profile.csv
runs/research_v173_timestamp_side_exposure_cap/v173_baseline_max_drawdown.csv
runs/research_v173_timestamp_side_exposure_cap/v173_selected_max_drawdown.csv
runs/research_v173_timestamp_side_exposure_cap/v173_timestamp_side_exposure_cap_summary.json
runs/research_v173_timestamp_side_exposure_cap/*_path.csv
reports/RESEARCH_V173_BTCUSDC_TIMESTAMP_SIDE_EXPOSURE_CAP.md
```

## Research Notes

- Base trades: V162 selected account path.
- Cap unit: same timestamp and same side.
- Cap action: scale all trades in the timestamp-side group when total `position_weight` exceeds the cap.
- V173 does not add trades, change side, change threshold, or promote live trading.
- This is a research risk audit, not a live trading guarantee.
