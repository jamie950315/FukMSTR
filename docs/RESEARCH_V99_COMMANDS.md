# Research V99 Commands

Run the fine-grained low-cost headroom scan for the BTCUSDC high-frequency HGB regime candidates:

```bash
make btcusdc-low-cost-headroom-v99
```

Run the focused V99 tests:

```bash
make test-btcusdc-v99
```

Outputs:

```text
runs/research_v99_btcusdc_low_cost_headroom/v99_low_cost_candidates.csv
runs/research_v99_btcusdc_low_cost_headroom/v99_low_cost_passed_candidates.csv
runs/research_v99_btcusdc_low_cost_headroom/v99_policy_headroom.csv
runs/research_v99_btcusdc_low_cost_headroom/v99_summary.json
reports/RESEARCH_V99_BTCUSDC_LOW_COST_HEADROOM_RESULTS.md
```

V99 keeps the V97 HGB candidate grid unchanged and replays the same candidate family under low-cost scenarios from 0 to 4 bps. The purpose is to measure whether the high-frequency route has any nonzero execution-cost headroom.
