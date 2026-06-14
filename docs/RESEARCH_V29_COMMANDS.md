# Research V29 Commands

V29 re-runs the V28 risk-gated BTCUSDC rolling validation over a longer year-to-date window.

## Run

```bash
make btcusdc-ytd-rolling-v29
```

Default range:

- Data: 2026-01-01 through 2026-06-10
- Calibration window: 20 days
- Validation window: 10 days
- Step: 10 days
- Risk gate: trade only when the selected calibration candidate has at least 25% account return at 8x

## Test

```bash
make test-btcusdc-v29
```

## Outputs

```text
runs/research_v29_btcusdc_ytd_rolling/summary_v28.json
runs/research_v29_btcusdc_ytd_rolling/REPORT_V28.md
runs/research_v29_btcusdc_ytd_rolling/btcusdc_v28_fold_metrics.csv
runs/research_v29_btcusdc_ytd_rolling/btcusdc_v28_candidate_evaluations.csv
runs/research_v29_btcusdc_ytd_rolling_input/downloaded_btcusdc_1m_klines.csv
runs/research_v29_btcusdc_ytd_rolling_input/ytd_rolling_run_summary.json
```

## Caveat

V29 is a failure audit. It exists to prevent over-reading V27/V28 as a stable long-run result.
