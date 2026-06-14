# Research V80 BTCUSDC Route Inventory Results

## Decision

- Promoted routes: ``
- Needs validation routes: ``
- Closed routes: `true_public_replay_baseline;sparse_tp;fixed_flow;direct_ml_1m;formal_family_selector`
- Next action: `create_new_hypothesis`

## Route Inventory

route,family,status,promoted,reason,metric,source
true_public_replay_baseline,baseline,closed,False,full_public_gate_failed,total=-84236.9648 bps; win_rate=0.1374,/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v26_btcusdc_full_public_replay/summary_v26.json
sparse_tp,sparse_take_profit,closed,False,true_btcusdc_replay_failed;v60_dense_holdout_not_fully_robust;design_robust_selector_failed_holdout,v64_pass_rate=0.9174; selected_holdout_pass_count=0,/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v67_btcusdc_sparse_tp_route_closure/v67_summary.json
fixed_flow,aggtrade_flow,closed,False,route_closure_failed_required_gates=v26_full_public_replay_gate;v68_base_fixed_flow_stability;v70_extended_validation_promoted;v72_execution_contract_and_stricter_checks;v75_design_selected_combined_policy_holdout;v77_bucket_transfer_stability;v78_prequential_bucket_guard_holdout,passed_required=0/7,/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v79_btcusdc_fixed_flow_route_closure/v79_summary.json
direct_ml_1m,direct_ml,closed,False,weak long-horizon signal only; not stable enough for promoted target,best_horizon_total=-363.9278 bps; gate_passed=False,/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v48_btcusdc_full_1m_direct_ml_probe/summary_v48.json
formal_family_selector,family_selector,closed,False,design-selected selectors failed holdout,best_total_policy=1440|30|flow_momentum|range_bps|0.8; best_total=3082.5335; selected_holdout_passed=False,/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v52_btcusdc_formal_family_probe/formal_family_probe_summary.json

## Interpretation

V80 finds no currently promoted BTCUSDC strategy route in the existing evidence. Sparse TP and fixed-flow are formally closed. Direct ML and formal family selectors do not have a promotion-grade holdout result. The next aligned work is to create or validate a genuinely new hypothesis, preferably with stronger out-of-sample evidence and execution modeling from the start.
