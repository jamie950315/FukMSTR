# Research V209 BTCUSDC Execution Provenance Gate

## Decision

- Status: `execution_provenance_blocked`
- Promote to real money: `False`
- Failed checks: `fill_evidence_available, filled_status_clean, execution_provenance_clean, slippage_p95_clean`
- Message: Do not use real money. Execution evidence provenance is missing or failed.

## Gate Checks

| Check | Passed | Evidence |
|---|---:|---|
| Fill evidence available | False | fill_count=0; missing_base_columns=['fill_price', 'intended_price', 'side', 'status', 'symbol', 'timestamp'] |
| Execution provenance clean | False | missing_provenance_columns=['capture_id', 'client_order_id', 'evidence_source', 'exchange_timestamp', 'execution_mode', 'order_id', 'venue'] |
| Filled status clean | False | requires every fill status to be `filled` |
| Slippage p95 clean | False | max_slippage_bps_p95=None |
| Kill switch tested | True | kill_switch_event_count=1 |
| Secrets absent from repo | True | secret_finding_count=0 |

## Iteration Metrics

| Metric | V209 |
|---|---:|
| Strategy thresholds changed | No |
| Entry/exit logic changed | No |
| Leverage logic changed | No |
| New backtest return improvement claimed | No |
| Places live orders | No |
| Execution provenance clean | False |
| Promote to real money | False |

## Interpretation

V209 tightens execution evidence admission. Clean-looking fills are not enough; real-money readiness now requires order-level provenance such as venue, execution mode, evidence source, capture id, order id, client order id, and exchange timestamp.

This does not create trades or claim new profitability. It prevents synthetic or backtest-like fill rows from satisfying the real-money execution gate.
