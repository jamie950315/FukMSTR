# Research V174 Commands

V174 compares the long rescue trades inside the V171 max-drawdown window against all other long rescue trades. It ranks pre-trade market-state differences so the next guard hypothesis can be based on observed state differences rather than a hard-coded drawdown event.

## Focused Test

```bash
make test-btcusdc-v174
```

## Run V174 Audit

```bash
make btcusdc-v174-long-rescue-state-audit
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

```text
runs/research_v174_long_rescue_state_audit/v174_long_rescue_marked.csv
runs/research_v174_long_rescue_state_audit/v174_long_rescue_group_summary.csv
runs/research_v174_long_rescue_state_audit/v174_long_rescue_feature_deltas.csv
runs/research_v174_long_rescue_state_audit/v174_long_rescue_state_audit_summary.json
reports/RESEARCH_V174_BTCUSDC_LONG_RESCUE_STATE_AUDIT.md
```

## Research Notes

- Base trades: V162 selected account path.
- Failure group: long rescue trades that also appear in the V171 max-drawdown window.
- Comparison group: all other long rescue trades.
- V174 does not add trades, change side, change threshold, or promote live trading.
- This is a research risk audit, not a live trading guarantee.
