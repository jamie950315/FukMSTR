# Research V171 Commands

V171 identifies the realized peak-to-trough max-drawdown window in the V162 selected account path, joins the V168 execution readiness gate, and attributes the drawdown window by side, leg, source, source-side-leg, and execution mode.

## Focused Test

```bash
make test-btcusdc-v171
```

## Run V171 Audit

```bash
make btcusdc-v171-max-drawdown-source-audit
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

```text
runs/research_v171_max_drawdown_source_audit/v171_annotated_drawdown_path.csv
runs/research_v171_max_drawdown_source_audit/v171_max_drawdown_window.csv
runs/research_v171_max_drawdown_source_audit/v171_side_attribution.csv
runs/research_v171_max_drawdown_source_audit/v171_leg_attribution.csv
runs/research_v171_max_drawdown_source_audit/v171_source_attribution.csv
runs/research_v171_max_drawdown_source_audit/v171_side_leg_attribution.csv
runs/research_v171_max_drawdown_source_audit/v171_source_side_leg_attribution.csv
runs/research_v171_max_drawdown_source_audit/v171_execution_mode_attribution.csv
runs/research_v171_max_drawdown_source_audit/v171_max_drawdown_source_audit_summary.json
reports/RESEARCH_V171_BTCUSDC_MAX_DRAWDOWN_SOURCE_AUDIT.md
```

## Research Notes

- Base trades: V162 selected account path.
- Execution mode source: V168 monthly execution readiness gate.
- Max drawdown window: trades after the latest equity peak through the max-drawdown trough.
- This audit does not add trades, change side, change threshold, or promote live trading.
- This is a research risk audit, not a live trading guarantee.
