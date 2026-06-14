# Research V164 Commands

V164 audits V162 robustness under extra execution cost, threshold movement, and sizing movement. It is a robustness audit only, not a new entry signal or a live-trading promotion.

## Focused Test

```bash
make test-btcusdc-v164
```

## Run V164 Audit

```bash
make btcusdc-v164-v162-robustness-audit
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

```text
runs/research_v164_v162_robustness_audit/v164_extra_cost_sensitivity.csv
runs/research_v164_v162_robustness_audit/v164_threshold_sensitivity.csv
runs/research_v164_v162_robustness_audit/v164_modifier_sensitivity.csv
runs/research_v164_v162_robustness_audit/v164_v162_robustness_audit_summary.json
reports/RESEARCH_V164_BTCUSDC_V162_ROBUSTNESS_AUDIT.md
```

## Research Notes

- Base robustness path: V162 selected account path.
- Extra execution cost is applied as `extra_cost_bps * account_leverage * position_weight` account bps per trade.
- Threshold sensitivity replays the V162 long trend-follow overlay from V161 with nearby thresholds.
- Modifier sensitivity replays the V162 overlay from V161 with nearby sizing values.
- The audit does not add trades, change sides, or promote the system for live trading.
- This is a research audit, not a live trading guarantee.
