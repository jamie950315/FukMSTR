# Research V85 BTCUSDC Rescue Hypothesis Closure Results

## Decision

- All required rescue hypotheses closed: `True`
- Open required hypotheses: ``
- Next action: `new_hypothesis_required`

## Evidence

hypothesis,version,required,closed,metric,reason,source
existing_route_inventory,V80,True,True,closed_routes=5; next_action=create_new_hypothesis,no existing promoted or needs-validation BTCUSDC route,/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v80_btcusdc_route_inventory/v80_summary.json
fixed_family_rescue,V81,True,True,families=1764; passed=0; best_positive_fold_rate=0.642857,no stable fixed family across YTD rolling validation,/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v81_btcusdc_fixed_family_viability/v81_summary.json
signal_inversion_rescue,V82,True,True,inverted_total=-81819.0352; inverted_fold_rate=0.0000; inverted_month_rate=0.0000,flipping direction remains deeply negative and unstable,/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v82_btcusdc_signal_inversion_audit/v82_summary.json
cost_edge_rescue,V83,True,True,scenarios=22; passed=0; best_cost=None,no original or inverted cost scenario passes gross-edge stability gate,/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v83_btcusdc_cost_edge_audit/v83_summary.json
pretrade_bucket_rescue,V84,True,True,passed_pretrade=0; passed_outcome=1,only outcome-only take-profit bucket passes; no pretrade subset passes,/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v84_btcusdc_exit_lane_bucket_audit/v84_summary.json

## Interpretation

V85 consolidates V80 through V84. Existing BTCUSDC routes are closed, fixed-family rescue fails, signal inversion fails, cost-edge rescue fails, and pretrade bucket rescue fails. The only passing subset is an outcome-only take-profit bucket, which cannot be used before entry.

This does not mean the overall research goal is complete. It means this rescue path is exhausted. The aligned next step is a genuinely new hypothesis or stronger data source, not another threshold or lane adjustment on the same BTCUSDC route family.
