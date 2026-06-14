# Research V39 Results

V39 audited whether BTCUSDC aggTrade-flow candidate families persist across completed folds. It ranks families only using prior completed validation outcomes, then selects the current fold's threshold by calibration score.

## Result

V39 did not pass the stability target.

| Config | Active windows | Passed windows | Total validation account return | Min validation account return |
|---|---:|---:|---:|---:|
| full_shape | 12 | 0 | -211.141126% | -83.290426% |
| coarse_shape | 12 | 0 | -491.944489% | -139.073560% |
| direction_feature | 12 | 0 | -330.338766% | -139.798898% |

## Interpretation

The family-persistence route does not solve the selector problem. Even after correcting the audit to collapse each fold/family to the candidate that would have been chosen by calibration score, no family selector passed any active validation window.

This reinforces the current root cause: BTCUSDC public-data candidates contain profitable hindsight choices, but the tested non-leaking selectors cannot identify them before validation.

## Outputs

```text
runs/research_v39_btcusdc_aggtrade_flow_ytd_family_selector/summary_v39.json
runs/research_v39_btcusdc_aggtrade_flow_ytd_family_selector/REPORT_V39.md
runs/research_v39_btcusdc_aggtrade_flow_ytd_family_selector/btcusdc_v39_family_selector_summary.csv
```
