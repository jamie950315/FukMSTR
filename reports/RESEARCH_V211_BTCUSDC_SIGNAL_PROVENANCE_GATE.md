# Research V211 BTCUSDC Signal Provenance Gate

## Decision

- Status: `signal_provenance_blocked`
- Promote to real money: `False`
- Failed checks: `signal_provenance_clean`
- Message: Do not use real money. Signal provenance is missing or failed.

## Gate Checks

| Check | Passed | Evidence |
|---|---:|---|
| Fill evidence available | False | fill_count=0; missing_base_columns=[] |
| Execution provenance clean | False | missing_provenance_columns=[] |
| Signal provenance clean | False | missing_signal_provenance_columns=[] |

## Iteration Metrics

| Metric | V211 |
|---|---:|
| Strategy thresholds changed | No |
| Entry/exit logic changed | No |
| Leverage logic changed | No |
| New backtest return improvement claimed | No |
| Places live orders | No |
| Signal provenance clean | False |
| Promote to real money | False |

## Interpretation

V211 prevents manual, synthetic, backtest, unknown, or blank signal/market sources from satisfying the execution-evidence path. Clean order-looking rows are not enough unless the signal source is also causal and auditable.

This does not create trades, tune thresholds, or claim new profitability. Real-money use remains blocked until V204 passes with current forward and execution evidence.
