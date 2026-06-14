# Research V93 Commands: BTCUSDC Short-Side Audit

V93 audits the short side of the current BTCUSDC main candidate, `v89_conservative_same_family_-550`, using the V92 full-window trade ledger. It does not retune thresholds or promote a modified strategy.

## Run Short-Side Audit

```bash
make btcusdc-short-side-audit-v93
```

## Test

```bash
make test-btcusdc-v93
```

## Outputs

```text
runs/research_v93_btcusdc_short_side_audit/v93_summary.json
runs/research_v93_btcusdc_short_side_audit/v93_side_summary.csv
runs/research_v93_btcusdc_short_side_audit/v93_short_months.csv
runs/research_v93_btcusdc_short_side_audit/v93_short_hours.csv
runs/research_v93_btcusdc_short_side_audit/v93_scenario_summary.csv
reports/RESEARCH_V93_BTCUSDC_SHORT_SIDE_AUDIT_RESULTS.md
```
