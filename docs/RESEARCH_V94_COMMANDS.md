# Research V94 Commands: BTCUSDC High-Frequency Scan

V94 runs a focused first-pass scan on BTCUSDC 1m aggTrade flow bars for higher-frequency candidates. It targets strategies with positive full-window and holdout PnL, win rate above 55%, and at least one trade per calendar day on average.

Run the scan:

```bash
make btcusdc-high-frequency-scan-v94
```

Run the focused V94 tests:

```bash
make test-btcusdc-v94
```

Outputs:

```text
runs/research_v94_btcusdc_high_frequency_scan/v94_summary.json
runs/research_v94_btcusdc_high_frequency_scan/v94_high_frequency_candidates.csv
runs/research_v94_btcusdc_high_frequency_scan/v94_high_frequency_passed_candidates.csv
reports/RESEARCH_V94_BTCUSDC_HIGH_FREQUENCY_SCAN_RESULTS.md
```

The scan computes thresholds on the design window and applies them to the full and holdout windows. It is a research scan, not a live trading guarantee.
