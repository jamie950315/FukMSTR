# Research V95 Commands: BTCUSDC TP/SL High-Frequency Scan

V95 runs a focused first-pass scan on BTCUSDC 1m aggTrade flow bars for higher-frequency TP/SL candidates. It targets strategies with positive full-window and holdout PnL, win rate above 55%, and at least one trade per calendar day on average.

Run the scan:

```bash
make btcusdc-tp-sl-high-frequency-scan-v95
```

Run the focused V95 tests:

```bash
make test-btcusdc-v95
```

Outputs:

```text
runs/research_v95_btcusdc_tp_sl_high_frequency_scan/v95_summary.json
runs/research_v95_btcusdc_tp_sl_high_frequency_scan/v95_tp_sl_high_frequency_candidates.csv
runs/research_v95_btcusdc_tp_sl_high_frequency_scan/v95_tp_sl_high_frequency_passed_candidates.csv
reports/RESEARCH_V95_BTCUSDC_TP_SL_HIGH_FREQUENCY_SCAN_RESULTS.md
```

The scan computes signal thresholds on the design window and applies them to the full and holdout windows. TP/SL hits that happen inside the same 1m bar are counted as stop-losses. It is a research scan, not a live trading guarantee.
