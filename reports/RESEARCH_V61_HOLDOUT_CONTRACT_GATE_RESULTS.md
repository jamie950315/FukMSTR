# Research V61 Holdout Contract Gate Results

## Purpose

V61 sends holdout-only sparse BTCUSDC ledgers through the unchanged V26 contract gate.

The main test is the V60 design-selected rule, selected using folds 1-4 only and evaluated here only on folds 5-7.

## Results

### V60 design-selected reversal 1080m q0.99

- Gate passed: `True`
- Failed checks: ``
- Holdout trades: `12`
- Holdout wins: `12`
- Holdout win rate: `1.000000`
- Holdout total net pnl: `858.000000` bps
- Holdout min trade net pnl: `71.500000` bps
- Contract account return: `68.640000%`

### Fixed V55/V57 reversal 1440m q0.995

- Gate passed: `False`
- Failed checks: `trade_count`
- Holdout trades: `7`
- Holdout wins: `7`
- Holdout win rate: `1.000000`
- Holdout total net pnl: `500.500000` bps
- Holdout min trade net pnl: `71.500000` bps
- Contract account return: `40.040000%`

## Files

- Summary JSON: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v61_btcusdc_sparse_tp_holdout_contract/v61_summary.json`

- v60_design_selected_reversal_1080_q099 entries: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v61_btcusdc_sparse_tp_holdout_contract/v61_v60_design_selected_reversal_1080_q099_holdout_entries.csv`
- v60_design_selected_reversal_1080_q099 contract source ledger: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v61_btcusdc_sparse_tp_holdout_contract/v61_v60_design_selected_reversal_1080_q099_holdout_source_ledger_for_contract_gate.csv`
- v60_design_selected_reversal_1080_q099 gate directory: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v61_v60_design_selected_reversal_1080_q099_holdout_contract_gate`
- fixed_v55_v57_reversal_1440_q0995 entries: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v61_btcusdc_sparse_tp_holdout_contract/v61_fixed_v55_v57_reversal_1440_q0995_holdout_entries.csv`
- fixed_v55_v57_reversal_1440_q0995 contract source ledger: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v61_btcusdc_sparse_tp_holdout_contract/v61_fixed_v55_v57_reversal_1440_q0995_holdout_source_ledger_for_contract_gate.csv`
- fixed_v55_v57_reversal_1440_q0995 gate directory: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v61_fixed_v55_v57_reversal_1440_q0995_holdout_contract_gate`

## Caveat

This is out-of-design relative to the V60 selector split, but it is still historical BTCUSDC data. It is not a substitute for future unseen data.
