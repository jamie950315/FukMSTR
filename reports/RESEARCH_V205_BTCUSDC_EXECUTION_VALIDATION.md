# Research V205 BTCUSDC Execution Validation

## Decision

- Status: `execution_validation_missing_evidence`
- Execution validation passed: `False`
- Failed checks: `fill_evidence_available, filled_status_clean, execution_provenance_clean, signal_provenance_clean, slippage_p95_clean, recent_execution_evidence_clean, paper_shadow_capture_summary_clean`
- Message: Do not use real money. Execution evidence is missing or failed.

## Inputs

- Fill audit CSV: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v205_execution_validation/fill_audit.csv`
- Kill-switch event CSV: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v205_execution_validation/kill_switch_events.csv`

## Gate Checks

| Check | Passed | Evidence |
|---|---:|---|
| Fill evidence available | False | fill_count=0; missing_base_columns=[]; missing_provenance_columns=[] |
| Filled status clean | False | requires every fill status to be `filled` |
| Execution provenance clean | False | requires venue, execution mode, evidence source, capture id, order id, client order id, and exchange timestamp |
| Signal provenance clean | False | missing_signal_provenance_columns=[]; blocks manual, synthetic, backtest, unknown, or blank signal/market sources |
| Slippage p95 clean | False | max_slippage_bps_p95=None |
| Recent execution evidence clean | False | latest_execution_timestamp=None; execution_evidence_age_days=None; max_age_days=7 |
| Paper-shadow capture summary clean | False | status=paper_shadow_fill_capture_blocked; reason=fill_evidence_unavailable |
| Kill switch tested | True | kill_switch_event_count=1 |
| Secrets absent from repo | True | secret_finding_count=0 |

## Iteration Metrics

| Metric | V205 |
|---|---:|
| Strategy thresholds changed | No |
| Entry/exit logic changed | No |
| Leverage logic changed | No |
| New backtest return improvement claimed | No |
| Places live orders | No |
| Execution validation passed | False |
| Fill evidence count | 0 |
| Execution provenance clean | False |
| Signal provenance clean | False |
| Recent execution evidence clean | False |
| Paper-shadow capture summary clean | False |
| Kill switch tested | True |
| Secrets present in repo | False |

## Interpretation

V205 does not place live orders and does not change the trading strategy. It only validates whether external execution evidence is strong enough for V204 to consider the execution gate.

This remains blocked for real-money use until clean fill evidence, order-level execution provenance, paper-shadow capture provenance where applicable, a tested kill switch, and a clean secret scan are all present.
