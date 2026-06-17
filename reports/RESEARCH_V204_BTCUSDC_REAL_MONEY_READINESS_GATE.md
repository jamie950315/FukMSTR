# Research V204 BTCUSDC Real-Money Readiness Gate

## Decision

- Status: `real_money_blocked`
- Promote to real money: `False`
- Failed checks: `historical_optimization_frozen_clean, forward_evidence_available, forward_freshness_clean, execution_validation_passed, execution_fill_evidence_available, filled_status_clean, execution_provenance_clean, signal_provenance_clean, execution_slippage_p95_clean, recent_execution_evidence_clean, paper_shadow_capture_summary_clean`
- Message: Do not use with real money. The failed checks must be resolved with new evidence first.

## Gate Checks

| Check | Passed | Evidence |
|---|---:|---|
| Readiness source provenance clean | True | source_commit=recorded_in_summary_json; dirty_runtime_path_count=0 |
| Readiness runtime source hash clean | True | runtime_source_hash=c53872f4f32f728f65c8c12e69d83f7e5677d11412684aaa5d171755b641a174 |
| Readiness input hashes clean | True | input_hash_count=6 |
| Historical optimization clean | False | overfit_status=post_goal_overfitting_warning; stop_historical_optimization=True |
| Forward evidence available | False | forward_status=no_forward_evidence; forward_trade_count=0 |
| Forward freshness clean | False | forward_freshness_status=forward_fresh_no_signal; forward_data_current=True; fresh_forward_evidence_available=False |
| Public data available | True | public_data_status=public_data_availability_passed; public_data_available=True; failed_checks=[] |
| Realtime smoke clean | True | rejected_signals=0; market_data_errors=0 |
| Execution validation passed | False | execution_status=execution_validation_missing_evidence; execution_validation_passed=False; failed_checks=['fill_evidence_available', 'filled_status_clean', 'execution_provenance_clean', 'signal_provenance_clean', 'slippage_p95_clean', 'recent_execution_evidence_clean', 'paper_shadow_capture_summary_clean'] |
| Execution fill evidence available | False | fill_count=0; min_execution_fills=30 |
| Filled status clean | False | filled_status_clean=False |
| Execution provenance clean | False | execution_provenance_clean=False |
| Signal provenance clean | False | signal_provenance_clean=False |
| Execution slippage p95 clean | False | max_slippage_bps_p95=None; slippage_p95_clean=False |
| Recent execution evidence clean | False | latest_execution_timestamp=None; execution_evidence_age_days=None |
| Paper-shadow capture summary clean | False | status=paper_shadow_fill_capture_blocked; reason=fill_evidence_unavailable |
| Execution kill switch tested | True | kill_switch_tested=True; execution_check=True |
| Execution secrets absent | True | secrets_present_in_repo=False; execution_check=True |

## Iteration Metrics

| Metric | V204 |
|---|---:|
| Strategy thresholds changed | No |
| Entry/exit logic changed | No |
| Leverage logic changed | No |
| New real-money readiness gate | True |
| Promote to real money | False |

## Interpretation

V204 is an admission gate, not a new trading strategy. It blocks real-money use when source provenance is missing, runtime source hashes are missing, input evidence hashes are missing, historical overfitting risk, missing forward evidence, missing forward freshness, incomplete public data, realtime smoke errors, missing execution validation, stale execution evidence, missing paper-shadow capture provenance, or missing execution/signal provenance are present.

This remains research and safety infrastructure until all gates pass with current evidence.
