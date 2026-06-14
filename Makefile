.PHONY: setup sample train-sample test real-tardis tune-real train-real-h10 diagnostics-h10 rules-h10 walk-forward-h10 clean

setup:
	python -m pip install -U pip
	python -m pip install -e .[dev]

sample:
	PYTHONPATH=src python -m lob_microprice_lab.cli generate-sample --out data/sample --rows 4000 --depth 10

train-sample:
	PYTHONPATH=src python -m lob_microprice_lab.cli train --book data/sample/book.csv --trades data/sample/trades.csv --config configs/example.yaml --out runs/sample

real-tardis:
	PYTHONPATH=src python -m lob_microprice_lab.cli fetch-tardis-sample --out data/real_tardis --depth 10 --sample-ms 500 --max-snapshots 10000

tune-real:
	PYTHONPATH=src python -m lob_microprice_lab.cli tune --book data/real_tardis/book_depth10_500ms.csv --config configs/example.yaml --out runs/real_tardis_tuning --horizons-sec 1,2,5 --thresholds-bps 0.25,0.5,1 --models logistic --edge-thresholds 0.05,0.10 --clean

train-real-h10:
	PYTHONPATH=src python -m lob_microprice_lab.cli train --book data/real_tardis/book_depth10_500ms.csv --config configs/real_h10_base.yaml --out runs/local_h10_base

diagnostics-h10:
	PYTHONPATH=src python -m lob_microprice_lab.cli diagnostics --book data/real_tardis/book_depth10_500ms.csv --config configs/real_h10_advanced.yaml --out runs/local_diagnostics_h10 --top-n 40 --clean

rules-h10:
	PYTHONPATH=src python -m lob_microprice_lab.cli rule-baselines --book data/real_tardis/book_depth10_500ms.csv --config configs/real_h10_advanced.yaml --out runs/local_rule_baselines_h10 --signal-thresholds 0,0.05,0.10,0.20,0.30,0.50,0.70 --clean

walk-forward-h10:
	PYTHONPATH=src python -m lob_microprice_lab.cli walk-forward --book data/real_tardis/book_depth10_500ms.csv --config configs/real_h10_base.yaml --out runs/local_walk_forward_h10 --horizon-sec 10 --threshold-bps 1 --model logistic --edge-threshold 0.5 --edge-thresholds 0.1,0.2,0.3,0.5,0.7,0.9 --folds 2 --min-train-ratio 0.5 --valid-ratio 0.15 --no-null --clean

test:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q

clean:
	rm -rf data/sample runs/sample runs/local_h10_base runs/local_diagnostics_h10 runs/local_rule_baselines_h10 runs/local_walk_forward_h10 .pytest_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +


test-split:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_features.py tests/test_labels.py tests/test_real_data.py tests/test_research_tools.py tests/test_stress.py tests/test_execution_v05.py tests/test_long_horizon.py tests/test_selective_v07.py tests/test_fixed_template_v08.py tests/test_trade_audit_v08.py tests/test_portfolio_v08.py tests/test_v09_research_tools.py tests/test_selection_bias_v10.py tests/test_sequential_selection_v11.py tests/test_slot_veto_v12.py tests/test_kline_features_v13.py tests/test_kline_weighting_v13.py tests/test_profit_stability_v14.py tests/test_kline_guard_v15.py tests/test_profit_success_fast_v15.py tests/test_profit_lock_v16.py tests/test_exit_lock_v17.py tests/test_profit_execution_lock_v17.py tests/test_deployment_lock_v18.py tests/test_real_fee_lock_v19.py
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_pipeline.py
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_diagnostics.py tests/test_adaptive.py


walk-forward-real:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli walk-forward --book data/real_tardis/book_depth10_500ms.csv --config configs/real_h10_base.yaml --out runs/local_walk_forward_h10_base --horizon-sec 10 --threshold-bps 1 --model logistic --edge-threshold 0.5 --edge-thresholds 0.1,0.2,0.3,0.5,0.7,0.9 --folds 2 --min-train-ratio 0.5 --valid-ratio 0.15 --no-null --clean


stress-h10-v04:
	PYTHONPATH=src python -m lob_microprice_lab.cli stress --predictions runs/research_v3_walk_forward_h10_base_2fold/oof_predictions.csv --out runs/local_v04_stress_h10 --horizon-sec 10 --edge-thresholds 0.3,0.5,0.7,0.9 --cost-bps-values 1.5,3.0 --latency-sec-values 0,0.5,1.0 --clean

adaptive-h5-v04:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli adaptive-walk-forward --book data/real_tardis/book_depth10_500ms.csv --config configs/real_h10_base.yaml --out runs/local_v04_adaptive_h5 --horizon-sec 5 --threshold-bps 1 --model logistic --candidate-edges 0.1,0.2,0.3,0.5,0.7,0.9 --cost-bps 1.5 --latency-sec 0 --folds 2 --min-train-ratio 0.5 --valid-ratio 0.15 --calibration-ratio 0.2 --min-calibration-trades 20 --clean


ensemble-h30-v05:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli ensemble-walk-forward --book data/real_tardis/book_depth10_500ms.csv --config configs/real_h30_v05.yaml --out runs/local_v05_ensemble_h30_taker --horizon-sec 30 --threshold-bps 1 --models logistic,hgb --candidate-edges 0.1,0.2,0.3,0.5,0.7 --cost-bps 1.5 --latency-sec 0.5 --stress-cost-bps-values 1.5,3.0 --stress-latency-sec-values 0,0.5,1.0 --folds 2 --min-train-ratio 0.5 --valid-ratio 0.15 --calibration-ratio 0.2 --top-k-features 80 --min-calibration-trades 10 --clean

rule-taker-h30-v05:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli rule-taker-walk-forward --book data/real_tardis/book_depth10_500ms.csv --config configs/real_h30_v05.yaml --out runs/local_v05_rule_taker_h30 --horizon-sec 30 --threshold-bps 1 --signal-thresholds 0,0.05,0.1,0.2,0.3,0.5,0.7 --candidate-edges 0.5 --cost-bps 1.5 --latency-sec 0.5 --stress-cost-bps-values 1.5,3.0 --stress-latency-sec-values 0,0.5,1.0 --folds 2 --min-train-ratio 0.5 --valid-ratio 0.15 --calibration-ratio 0.2 --min-calibration-trades 10 --clean

leakfree-h30-v06:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli ensemble-walk-forward --book data/real_tardis/book_depth10_500ms.csv --config configs/real_h30_v05.yaml --out runs/local_v06_leakfree_stationary_h30 --horizon-sec 30 --threshold-bps 1 --models logistic --candidate-edges 0.1,0.2,0.3,0.5,0.7 --cost-bps 1.5 --latency-sec 0.5 --stress-cost-bps-values 1.5,3.0,5.0 --stress-latency-sec-values 0,0.5,1.0,2.0 --folds 3 --min-train-ratio 0.45 --valid-ratio 0.12 --calibration-ratio 0.2 --top-k-features 80 --min-calibration-trades 8 --stationary-only --clean

leakfree-h45-v06:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli ensemble-walk-forward --book data/real_tardis/book_depth10_500ms.csv --config configs/real_h30_v05.yaml --out runs/local_v06_leakfree_stationary_h45 --horizon-sec 45 --threshold-bps 1 --models logistic --candidate-edges 0.1,0.2,0.3,0.5,0.7 --cost-bps 1.5 --latency-sec 0.5 --stress-cost-bps-values 1.5,3.0,5.0 --stress-latency-sec-values 0,0.5,1.0,2.0 --folds 3 --min-train-ratio 0.45 --valid-ratio 0.12 --calibration-ratio 0.2 --top-k-features 80 --min-calibration-trades 8 --stationary-only --clean

long-sweep-v06:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli long-horizon-sweep --book data/real_tardis/book_depth10_500ms.csv --config configs/real_h45_v06_long.yaml --out runs/local_v06_long_sweep --horizons-sec 30,45,60,90 --thresholds-bps 1 --model-sets 'logistic;logistic,hgb' --top-k-features 80,120 --candidate-edges 0.1,0.2,0.3,0.5,0.7 --cost-bps 1.5 --latency-sec 0.5 --stress-cost-bps-values 1.5,3.0,5.0 --stress-latency-sec-values 0,0.5,1.0,2.0 --folds 3 --min-train-ratio 0.45 --valid-ratio 0.12 --calibration-ratio 0.2 --min-calibration-trades 8 --stationary-only --clean

selective-h45-v07:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli selective-from-ensemble --ensemble-dir runs/research_v06_leakfree_stationary_logistic_h45_3fold_top80 --out runs/local_v07_selective_h45_nospread --horizon-sec 45 --cost-bps 1.5 --latency-sec 0.5 --edge-thresholds 0.2,0.5,0.7 --min-calibration-trades 8 --stress-cost-bps-values 1.5,3.0,5.0 --stress-latency-sec-values 0,0.5,1.0,2.0 --signed-columns imbalance_l3,microprice_dev_bps_l3,mid_ret_60r_bps --spread-quantiles 1.0 --vol-modes none --clean

fixed-template-h90-v08-source:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli fixed-template-audit --ensemble-dir runs/research_v07_long_sweep_stationary_logistic/h90p0_thr1p0_top80_logistic --out runs/local_v08_h90_source_rank --horizon-sec 90 --cost-bps 1.5 --latency-sec 0.5 --edge-thresholds 0.1,0.2,0.3,0.5,0.7 --signed-columns imbalance_l3,microprice_dev_bps_l3,mid_ret_60r_bps --spread-quantiles 1.0 --vol-modes none --template-source first_fold --selection-policy source_rank --min-source-trades 8 --top-k-templates 80 --stress-cost-bps-values 1.5,3.0,5.0 --stress-latency-sec-values 0,0.5,1.0,2.0 --clean

fixed-template-h90-v08-validation:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli fixed-template-audit --ensemble-dir runs/research_v07_long_sweep_stationary_logistic/h90p0_thr1p0_top80_logistic --out runs/local_v08_h90_validation_rank --horizon-sec 90 --cost-bps 1.5 --latency-sec 0.5 --edge-thresholds 0.1,0.2,0.3,0.5,0.7 --signed-columns imbalance_l3,microprice_dev_bps_l3,mid_ret_60r_bps --spread-quantiles 1.0 --vol-modes none --template-source first_fold --selection-policy validation_rank --min-source-trades 8 --top-k-templates 80 --stress-cost-bps-values 1.5,3.0,5.0 --stress-latency-sec-values 0,0.5,1.0,2.0 --clean

portfolio-v08-source:
	PYTHONPATH=src python -m lob_microprice_lab.cli combine-fixed-backtests --backtests runs/research_v08_fixed_template_h90_source_rank/selected_oof_backtest.csv runs/research_v08_fixed_template_h120_source_rank/selected_oof_backtest.csv runs/research_v08_fixed_template_h60_source_rank/selected_oof_backtest.csv runs/research_v08_fixed_template_h45_source_rank/selected_oof_backtest.csv --horizons-sec 90,120,60,45 --strategy-names h90_source,h120_source,h60_source,h45_source --out runs/local_v08_portfolio_source_rank --clean

portfolio-v08-validation:
	PYTHONPATH=src python -m lob_microprice_lab.cli combine-fixed-backtests --backtests runs/research_v08_fixed_template_h90_validation_rank/selected_oof_backtest.csv runs/research_v08_fixed_template_h120_validation_rank/selected_oof_backtest.csv runs/research_v08_fixed_template_h60_validation_rank/selected_oof_backtest.csv runs/research_v08_fixed_template_h45_validation_rank/selected_oof_backtest.csv --horizons-sec 90,120,60,45 --strategy-names h90_oracle,h120_oracle,h60_oracle,h45_oracle --out runs/local_v08_portfolio_validation_rank --clean


# V09 research targets
calibrated-edge-h90-v09:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli calibrated-edge-audit --ensemble-dir runs/research_v07_long_sweep_stationary_logistic/h90p0_thr1p0_top80_logistic --out runs/local_v09_calibrated_edge_h90 --horizon-sec 90 --cost-bps 1.5 --latency-sec 0.5 --calibrator logistic --edge-thresholds 0.05,0.1,0.2,0.3,0.5,0.7 --signed-columns imbalance_l3,microprice_dev_bps_l3,mid_ret_60r_bps --spread-quantiles 1.0 --vol-modes none --min-calibration-trades 4 --min-train-labels 50 --stress-cost-bps-values 1.5,3.0,5.0 --stress-latency-sec-values 0,0.5,1.0,2.0 --clean

family-h90-v09:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli family-adaptive-audit --ensemble-dir runs/research_v07_long_sweep_stationary_logistic/h90p0_thr1p0_top80_logistic --family-json runs/research_v08_fixed_template_h90_validation_rank/selected_candidate.json --out runs/local_v09_family_h90 --horizon-sec 90 --cost-bps 1.5 --latency-sec 0.5 --edge-thresholds 0.1,0.2,0.3,0.5,0.7 --signed-abs-quantiles 0,0.25,0.5,0.75,0.9 --spread-quantiles 1.0 --vol-modes none --min-calibration-trades 4 --stress-cost-bps-values 1.5,3.0,5.0 --stress-latency-sec-values 0,0.5,1.0,2.0 --clean

template-transfer-h90-v09:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli template-transfer-audit --ensemble-dir runs/research_v07_long_sweep_stationary_logistic/h90p0_thr1p0_top80_logistic --out runs/local_v09_template_transfer_h90 --horizon-sec 90 --cost-bps 1.5 --latency-sec 0.5 --edge-thresholds 0.1,0.2,0.3,0.5,0.7 --signed-columns imbalance_l3,microprice_dev_bps_l3,mid_ret_60r_bps --spread-quantiles 1.0 --vol-modes none --min-source-trades 4 --top-k-templates 80 --warmup-folds 1 --min-history-trades 3 --stress-cost-bps-values 1.5,3.0,5.0 --stress-latency-sec-values 0,0.5,1.0,2.0 --clean

# V10 research targets: family-wise null correction for long-window template search
family-null-h90-v10:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli template-family-null-audit --ensemble-dir runs/research_v07_long_sweep_stationary_logistic/h90p0_thr1p0_top80_logistic --out runs/local_v10_family_null_h90 --horizon-sec 90 --cost-bps 1.5 --latency-sec 0.5 --edge-thresholds 0.1,0.2,0.3,0.5,0.7 --signed-columns imbalance_l3,microprice_dev_bps_l3,mid_ret_60r_bps --spread-quantiles 1.0 --vol-modes none --template-source first_fold --min-source-trades 4 --top-k-templates 80 --shift-runs 80 --stress-cost-bps-values 1.5,3.0,5.0 --stress-latency-sec-values 0,0.5,1.0,2.0 --clean

family-null-h120-v10:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli template-family-null-audit --ensemble-dir runs/research_v07_long_sweep_stationary_logistic/h120p0_thr1p0_top80_logistic --out runs/local_v10_family_null_h120 --horizon-sec 120 --cost-bps 1.5 --latency-sec 0.5 --edge-thresholds 0.1,0.2,0.3,0.5,0.7 --signed-columns imbalance_l3,microprice_dev_bps_l3,mid_ret_60r_bps --spread-quantiles 1.0 --vol-modes none --template-source first_fold --min-source-trades 4 --top-k-templates 80 --shift-runs 80 --stress-cost-bps-values 1.5,3.0,5.0 --stress-latency-sec-values 0,0.5,1.0,2.0 --clean

# V11 research targets: online/prequential template selection stress
sequential-h90-v11-source:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli sequential-template-audit --ensemble-dir runs/research_v09_ensemble_h90_5fold_stationary --out runs/local_v11_seq_h90_5fold_source --horizon-sec 90 --cost-bps 1.5 --latency-sec 0.5 --edge-thresholds 0.1,0.2,0.3,0.5,0.7 --signed-columns imbalance_l3,microprice_dev_bps_l3,mid_ret_60r_bps --spread-quantiles 1.0 --vol-modes none --template-source first_fold --min-source-trades 4 --top-k-templates 80 --period-sec 0 --ranking-policy source_rank --cold-start-policy source_rank --warmup-periods 0 --min-history-trades 0 --min-history-periods 0 --shift-null-runs 80 --stress-cost-bps-values 1.5,3.0,5.0 --stress-latency-sec-values 0,0.5,1.0,2.0 --gate-min-oof-trades 20 --gate-min-periods-with-trades 5 --gate-min-period-mean-net-bps 0 --clean

sequential-h90-v11-lower:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli sequential-template-audit --ensemble-dir runs/research_v09_ensemble_h90_5fold_stationary --out runs/local_v11_seq_h90_5fold_lower --horizon-sec 90 --cost-bps 1.5 --latency-sec 0.5 --edge-thresholds 0.1,0.2,0.3,0.5,0.7 --signed-columns imbalance_l3,microprice_dev_bps_l3,mid_ret_60r_bps --spread-quantiles 1.0 --vol-modes none --template-source first_fold --min-source-trades 4 --top-k-templates 80 --period-sec 0 --ranking-policy past_lower_bound --cold-start-policy source_rank --warmup-periods 1 --min-history-trades 3 --min-history-periods 1 --min-lower-bound-bps 0 --shift-null-runs 40 --stress-cost-bps-values 1.5,3.0,5.0 --stress-latency-sec-values 0,0.5,1.0,2.0 --gate-min-oof-trades 20 --gate-min-periods-with-trades 3 --gate-min-period-mean-net-bps 0 --clean

sequential-h90-v11-microperiod:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli sequential-template-audit --ensemble-dir runs/research_v09_ensemble_h90_5fold_stationary --out runs/local_v11_seq_h90_5fold_source_p180 --horizon-sec 90 --cost-bps 1.5 --latency-sec 0.5 --edge-thresholds 0.1,0.2,0.3,0.5,0.7 --signed-columns imbalance_l3,microprice_dev_bps_l3,mid_ret_60r_bps --spread-quantiles 1.0 --vol-modes none --template-source first_fold --min-source-trades 4 --top-k-templates 20 --period-sec 180 --ranking-policy source_rank --cold-start-policy source_rank --warmup-periods 0 --min-history-trades 0 --min-history-periods 0 --shift-null-runs 30 --stress-cost-bps-values 1.5,3.0,5.0 --stress-latency-sec-values 0,0.5,1.0,2.0 --gate-min-oof-trades 20 --gate-min-periods-with-trades 5 --gate-min-period-mean-net-bps 0 --clean

family-null-h90-v11-5fold:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli template-family-null-audit --ensemble-dir runs/research_v09_ensemble_h90_5fold_stationary --out runs/local_v11_family_null_h90_5fold --horizon-sec 90 --cost-bps 1.5 --latency-sec 0.5 --edge-thresholds 0.1,0.2,0.3,0.5,0.7 --signed-columns imbalance_l3,microprice_dev_bps_l3,mid_ret_60r_bps --spread-quantiles 1.0 --vol-modes none --template-source first_fold --min-source-trades 4 --top-k-templates 80 --shift-runs 60 --stress-cost-bps-values 1.5,3.0,5.0 --stress-latency-sec-values 0,0.5,1.0,2.0 --clean

# V12 research target: conservative slot-preserving OFI veto on the H90 5-fold lead
slot-veto-h90-v12:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli slot-veto-audit --ensemble-dir runs/research_v09_ensemble_h90_5fold_stationary --out runs/local_v12_slot_veto_h90_ofi_l5_q90 --horizon-sec 90 --cost-bps 1.5 --latency-sec 0.5 --edge-threshold 0.1 --filter-col ofi_sum_l5_norm --filter-operator '<=' --filter-quantile 0.9 --family-filter-cols ofi_sum_l3_norm,ofi_sum_l5_norm,ofi_sum_l10_norm --family-quantiles 0.5,0.6,0.7,0.8,0.9 --stress-cost-bps-values 1.5,3.0,5.0 --stress-latency-sec-values 0,0.5,1.0,2.0 --shift-null-runs 80 --family-shift-runs 80 --gate-min-oof-trades 20 --gate-min-periods-with-trades 5 --gate-min-period-mean-net-bps 0 --gate-max-family-null-p-total 0.05 --gate-max-family-null-p-mean 0.10 --clean

# V13 research targets: multi-timeframe K-line features and fixed K-line blend overlay
kline-cache-v13:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli build-kline-cache --book data/real_tardis/book_depth10_500ms.csv --out runs/local_v13_kline_cache.csv --timeframes 1s,5s,15s,1m,5m,15m --lookbacks 1,3,6,12 --decision-lag-sec 0

kline-h90-v13-v12folds:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli ensemble-walk-forward --book data/real_tardis/book_depth10_500ms.csv --config runs/research_v09_ensemble_h90_5fold_stationary/config_resolved.yaml --out runs/local_v13_kline_h90_5fold_stationary_v12folds --horizon-sec 90 --threshold-bps 1 --models logistic --candidate-edges 0.1,0.2,0.3,0.5,0.7 --cost-bps 1.5 --latency-sec 0.5 --stress-cost-bps-values 1.5,3.0,5.0 --stress-latency-sec-values 0,0.5,1.0,2.0 --folds 5 --min-train-ratio 0.35 --valid-ratio 0.10 --calibration-ratio 0.2 --top-k-features 80 --min-calibration-trades 4 --stationary-only --kline-timeframes 1s,5s,15s,1m,5m,15m --kline-lookbacks 1,3,6,12 --kline-decision-lag-sec 0 --clean

kline-blend-alpha010-v13:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli kline-blend-ensemble --base-ensemble-dir runs/research_v09_ensemble_h90_5fold_stationary --kline-ensemble-dir runs/local_v13_kline_h90_5fold_stationary_v12folds --out runs/local_v13_kline_blend_alpha010_h90_pruned --kline-alpha 0.1 --drop-kline-feature-columns --clean

slot-veto-kline-blend-v13:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli slot-veto-audit --ensemble-dir runs/local_v13_kline_blend_alpha010_h90_pruned --out runs/local_v13_slot_veto_kline_blend_alpha010_h90 --horizon-sec 90 --cost-bps 1.5 --latency-sec 0.5 --edge-threshold 0.1 --filter-col ofi_sum_l5_norm --filter-operator '<=' --filter-quantile 0.9 --family-filter-cols ofi_sum_l3_norm,ofi_sum_l5_norm,ofi_sum_l10_norm --family-quantiles 0.5,0.6,0.7,0.8,0.9 --stress-cost-bps-values 1.5,3.0,5.0 --stress-latency-sec-values 0,0.5,1.0,2.0 --shift-null-runs 80 --family-shift-runs 80 --gate-min-oof-trades 20 --gate-min-periods-with-trades 5 --gate-min-period-mean-net-bps 0 --gate-max-family-null-p-total 0.05 --gate-max-family-null-p-mean 0.10 --clean

kline-weight-h90-v13:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli kline-weight-audit --ensemble-dir runs/local_v13_kline_h90_5fold_stationary_v12folds --out runs/local_v13_kline_weight_h90_v12folds --horizon-sec 90 --cost-bps 1.5 --latency-sec 0.5 --edge-thresholds 0.05,0.1,0.2,0.3,0.5 --base-weight-values 0,0.25,0.5,0.75,1.0 --kline-signs=-1,1 --min-calibration-trades 4 --stress-cost-bps-values 1.5,3.0,5.0 --stress-latency-sec-values 0,0.5,1.0,2.0 --shift-null-runs 40 --gate-min-oof-trades 20 --gate-min-folds-with-trades 5 --gate-min-fold-mean-net-bps 0 --gate-max-shift-null-p-total 0.10 --gate-max-shift-null-p-mean 0.10 --clean

# Research V14: fixed K-line stability lock with alpha/OFI family null correction
kline-stability-lock-v14:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli kline-stability-lock-audit --base-ensemble-dir runs/research_v09_ensemble_h90_5fold_stationary --kline-ensemble-dir runs/research_v13_kline_h90_5fold_stationary_v12folds --out runs/local_v14_kline_stability_lock_alpha0125_h90 --horizon-sec 90 --cost-bps 1.5 --latency-sec 0.5 --selected-alpha 0.125 --alpha-grid 0,0.025,0.05,0.075,0.1,0.125,0.15 --edge-threshold 0.1 --filter-col ofi_sum_l5_norm --filter-operator '<=' --filter-quantile 0.9 --family-filter-cols ofi_sum_l3_norm,ofi_sum_l5_norm,ofi_sum_l10_norm --family-quantiles 0.5,0.6,0.7,0.8,0.9 --stress-cost-bps-values 1.5,3.0,5.0 --stress-latency-sec-values 0,0.5,1.0,2.0 --shift-null-runs 80 --gate-max-family-p 0.05 --write-selected-blend-dir runs/local_v14_kline_blend_alpha0125_h90_pruned --clean


# Research V15: K-line support guard after V14 stability lock
kline-support-guard-v15:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli kline-guard-audit --base-ensemble-dir runs/research_v09_ensemble_h90_5fold_stationary --kline-ensemble-dir runs/research_v13_kline_h90_5fold_stationary_v12folds --out runs/research_v15_kline_support_guard_alpha0125_h90 --horizon-sec 90 --cost-bps 1.5 --latency-sec 0.5 --edge-threshold 0.1 --kline-alpha 0.125 --ofi-col ofi_sum_l5_norm --ofi-quantile 0.9 --kline-col kline_15s_rv_6_bps --kline-quantile 0.0 --kline-operator '>=' --directional --family-kline-cols kline_15s_rv_6_bps,kline_15s_rv_12_bps,kline_1m_rv_3_bps,kline_1m_range_z_6,kline_1s_rv_1_bps,kline_15m_ret_3_bps,kline_15s_signal --family-kline-quantiles 0.0 --stress-cost-bps-values 1.5,3.0,5.0 --stress-latency-sec-values 0,0.5,1.0,2.0 --shift-null-runs 40 --family-shift-runs 40 --gate-min-oof-trades 20 --gate-min-periods-with-trades 5 --gate-min-period-mean-net-bps 0 --gate-max-family-null-p-total 0.05 --gate-max-family-null-p-mean 0.10 --clean

# Research V15: fast triple-family profit success audit. This avoids materializing hundreds of K-line columns in null loops.
profit-success-fast-v15:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_profit_success_fast_v15.py


# Research V16: frozen V15 policy profit-lock certificate with sparse 1000-shift nulls and extended stress.
profit-lock-v16:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_profit_lock_v16.py

# Research V17: slot-preserving execution lock on top of the frozen V15/V16 entry policy.
execution-lock-v17:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_profit_exit_lock_v17.py

# Research V17: frozen V15/V16 entry plus slot-preserving take-profit execution lock certificate.
execution-profit-lock-v17:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_profit_execution_lock_v17.py

# Research V18: deployment-readiness lock over the frozen V17 execution-profit ledger.
deployment-lock-v18:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_deployment_lock_v18.py

# Research V19: user real fee lock, taker 0.0400%, maker 0.0000%.
real-fee-lock-v19:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_real_fee_lock_v19.py

# Research V20: BTC contract data source plan.
btc-contract-data-plan-v20:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python -m lob_microprice_lab.cli btc-contract-data-plan --out runs/research_v20_btc_contract_data_plan --symbol BTCUSDT --start-date 2024-01-01 --end-date 2026-06-10

# Research V20: BTC contract side guard plus leverage scenarios.
btc-contract-leverage-v20:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btc_contract_leverage_lock_v20.py

# V20 final promoted target: BTC-specific side guard plus leverage certificate.
btc-leverage-lock-v20-final:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btc_contract_leverage_lock_v20.py


# Research V21: BTC profit target lock, V20 entry rule plus audited 45 bps take-profit target.
btc-profit-target-lock-v21:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btc_profit_target_lock_v21.py

# Research V22: BTC rescue profit lock, V20/V21 BTC rule plus audited long rescue lane and 52 bps take-profit target.
btc-rescue-profit-lock-v22:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btc_rescue_profit_lock_v22.py

# Latest BTC research tests.
test-btc-v22:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btc_contract_data_v20.py tests/test_btc_contract_leverage_v20.py tests/test_btc_leverage_lock_v20.py tests/test_btc_profit_target_lock_v21.py tests/test_btc_rescue_profit_lock_v22.py

btc-adaptive-safety-lock-v23:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btc_adaptive_safety_lock_v23.py

test-btc-v23:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btc_adaptive_safety_lock_v23.py

# Research V24: BTC adaptive exit lock, V22 entries plus asymmetric slot-preserving take-profit ladder.
btc-adaptive-exit-lock-v24:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btc_adaptive_exit_lock_v24.py

test-btc-v24-exit:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btc_adaptive_exit_lock_v24.py tests/test_btc_rescue_profit_lock_v22.py

btc-adaptive-exit-safety-lock-v24:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btc_adaptive_exit_safety_lock_v24.py

test-btc-v24:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btc_adaptive_exit_safety_lock_v24.py tests/test_btc_adaptive_safety_lock_v23.py tests/test_btc_adaptive_exit_lock_v24.py tests/test_btc_rescue_profit_lock_v22.py

# Research V25 additional audit: four-loss safety certificate.
btc-four-loss-safety-lock-v25:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btc_four_loss_safety_lock_v25.py

test-btc-v25-four-loss:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btc_four_loss_safety_lock_v25.py tests/test_btc_adaptive_exit_safety_lock_v24.py tests/test_btc_adaptive_exit_lock_v24.py tests/test_btc_rescue_profit_lock_v22.py

# Research V25: BTC portfolio risk lock, V24 frozen trades plus emergency four-loss survival governor.
btc-portfolio-risk-lock-v25:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btc_portfolio_risk_lock_v25.py

test-btc-v25-portfolio:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btc_portfolio_risk_lock_v25.py tests/test_btc_adaptive_exit_safety_lock_v24.py

# Research V26: BTCUSDC contract lock, frozen BTC rule transferred to BTCUSDC with quote-market surcharge and BTCUSDC data manifest.
btcusdc-contract-lock-v26:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_contract_lock_v26.py

btcusdc-true-replay-v26:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_true_replay_v26.py

# Research V27: BTCUSDC independent public 1m kline calibration/validation audit.
btcusdc-independent-validation-v27:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_independent_validation_v27.py

btcusdc-rolling-forward-v28:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_rolling_forward_v28.py

btcusdc-ytd-rolling-v29:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_ytd_rolling_v29.py

btcusdc-oracle-gap-v30:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_oracle_gap_v30.py

btcusdc-prequential-selector-v31:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_prequential_selector_v31.py

btcusdc-aggtrade-flow-v32:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_aggtrade_flow_v32.py

btcusdc-aggtrade-flow-rolling-v33:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_aggtrade_flow_rolling_v33.py

btcusdc-aggtrade-flow-ytd-rolling-v36:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_aggtrade_flow_ytd_rolling_v36.py

btcusdc-aggtrade-flow-ytd-oracle-gap-v37:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_aggtrade_flow_ytd_oracle_gap_v37.py

btcusdc-aggtrade-flow-ytd-prequential-selector-v38:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_aggtrade_flow_ytd_prequential_selector_v38.py

btcusdc-aggtrade-flow-ytd-family-selector-v39:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_aggtrade_flow_ytd_family_selector_v39.py

btcusdc-topk-portfolio-v40:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_topk_portfolio_v40.py

btcusdc-aggtrade-5s-probe-v41:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_aggtrade_5s_probe_v41.py

btcusdc-quantile-band-selector-v42:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_quantile_band_selector_v42.py

btcusdc-nested-recency-v43:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_nested_recency_v43.py

btcusdc-prequential-meta-selector-v44:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_prequential_meta_selector_v44.py

btcusdc-enhanced-meta-selector-v45:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_enhanced_meta_selector_v45.py

btcusdc-fixed-family-transfer-v46:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_fixed_family_transfer_v46.py

btcusdc-hourly-gate-v47:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_hourly_gate_v47.py

btcusdc-full-1m-direct-ml-v48:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_full_1m_direct_ml_v48.py

btcusdc-sparse-tp-exit-v54:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_sparse_tp_exit_v54.py

btcusdc-sparse-tp-next-open-v55:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_sparse_tp_next_open_v55.py

btcusdc-sparse-tp-entry-delay-v56:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_sparse_tp_entry_delay_v56.py

btcusdc-sparse-tp-kline-confirm-v57:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_sparse_tp_kline_confirm_v57.py

btcusdc-sparse-tp-null-audit-v58:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_sparse_tp_null_audit_v58.py

btcusdc-sparse-tp-neighborhood-v59:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_sparse_tp_neighborhood_v59.py

btcusdc-sparse-tp-design-selector-v60:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_sparse_tp_design_selector_v60.py

btcusdc-sparse-tp-holdout-contract-v61:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_sparse_tp_holdout_contract_v61.py

btcusdc-sparse-tp-holdout-entry-delay-v62:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_sparse_tp_holdout_entry_delay_v62.py

btcusdc-sparse-tp-delay5-anomaly-v63:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_sparse_tp_delay5_anomaly_v63.py

btcusdc-sparse-tp-dense-delay-scan-v64:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_sparse_tp_dense_delay_scan_v64.py

btcusdc-sparse-tp-signal-fragility-v65:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_sparse_tp_signal_fragility_v65.py

btcusdc-sparse-tp-design-robust-selector-v66:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_sparse_tp_design_robust_selector_v66.py

btcusdc-sparse-tp-route-closure-v67:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_sparse_tp_route_closure_v67.py

btcusdc-fixed-flow-stability-v68:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_fixed_flow_stability_v68.py

btcusdc-fixed-flow-hour-gate-v69:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_fixed_flow_hour_gate_v69.py

btcusdc-fixed-flow-extended-validation-v70:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_fixed_flow_v70_extended_validation.py

test-btcusdc-v26:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v27:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v28:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v29:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v30:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v31:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v32:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v33:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v36:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v38:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v39:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v40:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v41:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v42:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v43:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v44:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v45:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v46:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v47:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v48:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v54:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_sparse_tp_v54.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v55:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_sparse_tp_v54.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v56:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_sparse_tp_v54.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v57:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_sparse_tp_v54.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v58:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_sparse_tp_v54.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v59:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_sparse_tp_v54.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v60:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_sparse_tp_v54.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v61:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_sparse_tp_v54.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v62:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_sparse_tp_v54.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v63:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_sparse_tp_v54.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v64:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_sparse_tp_v54.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v65:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_sparse_tp_v54.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v66:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_sparse_tp_v54.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v67:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_sparse_tp_v54.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v68:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v69:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

test-btcusdc-v70:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

btcusdc-fixed-flow-dense-delay-stress-v71:
	PYTHONPATH=src python scripts/run_btcusdc_fixed_flow_v71_dense_delay_stress.py

test-btcusdc-v71:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

btcusdc-fixed-flow-cost-delay-contract-v72:
	PYTHONPATH=src python scripts/run_btcusdc_fixed_flow_v72_cost_delay_contract.py

test-btcusdc-v72:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

btcusdc-fixed-flow-monthly-cooldown-v73:
	PYTHONPATH=src python scripts/run_btcusdc_fixed_flow_v73_monthly_cooldown.py

test-btcusdc-v73:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

btcusdc-fixed-flow-combined-contract-v74:
	PYTHONPATH=src python scripts/run_btcusdc_fixed_flow_v74_combined_contract.py

test-btcusdc-v74:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

btcusdc-fixed-flow-design-selected-combined-policy-v75:
	PYTHONPATH=src python scripts/run_btcusdc_fixed_flow_v75_design_selected_combined_policy.py

test-btcusdc-v75:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

btcusdc-fixed-flow-holdout-failure-attribution-v76:
	PYTHONPATH=src python scripts/run_btcusdc_fixed_flow_v76_holdout_failure_attribution.py

test-btcusdc-v76:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

btcusdc-fixed-flow-bucket-transfer-stability-v77:
	PYTHONPATH=src python scripts/run_btcusdc_fixed_flow_v77_bucket_transfer_stability.py

test-btcusdc-v77:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

btcusdc-fixed-flow-prequential-bucket-guard-v78:
	PYTHONPATH=src python scripts/run_btcusdc_fixed_flow_v78_prequential_bucket_guard.py

test-btcusdc-v78:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

btcusdc-fixed-flow-route-closure-v79:
	PYTHONPATH=src python scripts/run_btcusdc_fixed_flow_v79_route_closure.py

test-btcusdc-v79:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

btcusdc-route-inventory-v80:
	PYTHONPATH=src python scripts/run_btcusdc_v80_route_inventory.py

test-btcusdc-v80:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

btcusdc-fixed-family-viability-v81:
	PYTHONPATH=src python scripts/run_btcusdc_v81_fixed_family_viability.py

test-btcusdc-v81:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

btcusdc-signal-inversion-audit-v82:
	PYTHONPATH=src python scripts/run_btcusdc_v82_signal_inversion_audit.py

test-btcusdc-v82:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

btcusdc-cost-edge-audit-v83:
	PYTHONPATH=src python scripts/run_btcusdc_v83_cost_edge_audit.py

test-btcusdc-v83:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

btcusdc-exit-lane-bucket-audit-v84:
	PYTHONPATH=src python scripts/run_btcusdc_v84_exit_lane_bucket_audit.py

test-btcusdc-v84:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

btcusdc-rescue-closure-v85:
	PYTHONPATH=src python scripts/run_btcusdc_v85_rescue_closure.py

test-btcusdc-v85:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

btcusdc-short-term-recent-validation-v86:
	PYTHONPATH=src python scripts/run_btcusdc_v86_short_term_recent_validation.py

test-btcusdc-v86:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

btcusdc-recent-repair-validation-v87:
	PYTHONPATH=src python scripts/run_btcusdc_v87_recent_repair_validation.py

test-btcusdc-v87:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

btcusdc-v87-two-year-stability-v88:
	PYTHONPATH=src python scripts/run_btcusdc_v88_v87_two_year_stability.py

test-btcusdc-v88:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

btcusdc-stability-improvement-scan-v89:
	PYTHONPATH=src python scripts/run_btcusdc_v89_stability_improvement_scan.py

test-btcusdc-v89:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

btcusdc-forward-monitoring-v90:
	PYTHONPATH=src python scripts/run_btcusdc_v90_forward_monitoring.py

test-btcusdc-v90:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_direct_ml_v48.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py

btcusdc-v90-two-year-window:
	PYTHONPATH=src python scripts/run_btcusdc_v90_two_year_window.py

ethusdc-v90-transfer-test-v91:
	PYTHONPATH=src python scripts/run_ethusdc_v90_transfer_test.py

test-ethusdc-v91:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_eth_v90_runner_builds_symbol_specific_monthly_and_daily_paths

btcusdc-v92-earliest-to-latest-window:
	PYTHONPATH=src python scripts/run_btcusdc_v92_earliest_to_latest_window.py

test-btcusdc-v92:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v92_runner_uses_full_available_bar_window tests/test_btcusdc_independent_validation_v27.py::test_v90_mechanical_policy_preserves_v87_short_veto

btcusdc-short-side-audit-v93:
	PYTHONPATH=src python scripts/run_btcusdc_v93_short_side_audit.py

test-btcusdc-v93:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v93_side_summary_splits_long_and_short_metrics

btcusdc-high-frequency-scan-v94:
	PYTHONPATH=src python scripts/run_btcusdc_v94_high_frequency_scan.py

test-btcusdc-v94:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v94_high_frequency_gate_requires_daily_frequency_and_holdout_profit tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v94_daily_frequency_summary_counts_calendar_days tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v94_spaced_indices_matches_greedy_non_overlap

btcusdc-tp-sl-high-frequency-scan-v95:
	PYTHONPATH=src python scripts/run_btcusdc_v95_tp_sl_high_frequency_scan.py

test-btcusdc-v95:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v95_barrier_ledger_uses_conservative_same_bar_stop tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v95_barrier_ledger_handles_short_take_profit tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v95_gate_requires_win_frequency_and_holdout_profit

btcusdc-ml-probability-gate-v96:
	PYTHONPATH=src python scripts/run_btcusdc_v96_ml_probability_gate.py

test-btcusdc-v96:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v96_labels_fee_adjusted_up_down_and_flat tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v96_prediction_ledger_uses_probability_side_and_spacing tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v96_gate_requires_selector_and_holdout_quality

btcusdc-hgb-regime-gate-v97:
	PYTHONPATH=src python scripts/run_btcusdc_v97_hgb_regime_gate.py

test-btcusdc-v97:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v97_regime_mask_uses_selector_quantiles_only tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v97_gate_requires_selector_and_holdout_quality

btcusdc-cost-sensitivity-v98:
	PYTHONPATH=src python scripts/run_btcusdc_v98_cost_sensitivity.py

test-btcusdc-v98:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v98_adjusts_fee_from_gross_without_changing_trades tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v98_cost_gate_requires_frequency_win_and_profit tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v98_decision_does_not_treat_zero_fee_only_as_realistic_completion

btcusdc-low-cost-headroom-v99:
	PYTHONPATH=src python scripts/run_btcusdc_v99_low_cost_headroom.py

test-btcusdc-v99:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v99_policy_headroom_uses_max_passing_fee tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v99_decision_requires_nonzero_fee_headroom

btcusdc-maker-fill-risk-v100:
	PYTHONPATH=src python scripts/run_btcusdc_v100_maker_fill_risk.py

test-btcusdc-v100:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v100_adverse_fill_keeps_worst_trades_and_extra_cost tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v100_decision_requires_all_required_stresses_to_pass

btcusdc-thick-edge-regression-v101:
	PYTHONPATH=src python scripts/run_btcusdc_v101_thick_edge_regression.py

test-btcusdc-v101:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v101_edge_prediction_ledger_uses_signed_edge_and_spacing tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v101_gate_requires_profit_win_frequency_and_months

btcusdc-ma-feature-regression-v102:
	PYTHONPATH=src python scripts/run_btcusdc_v102_ma_feature_regression.py

test-btcusdc-v102:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v102_ma_features_use_prior_close_without_lookahead tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v102_feature_frame_includes_ma_columns

btcusdc-daily-topk-ma-regression-v103:
	PYTHONPATH=src python scripts/run_btcusdc_v103_daily_topk_ma_regression.py

test-btcusdc-v103:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v103_daily_topk_ledger_selects_ranked_non_overlapping_predictions tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v103_gate_requires_profit_win_frequency_and_months

btcusdc-ma-hgb-daily-topk-classifier-v104:
	PYTHONPATH=src python scripts/run_btcusdc_v104_ma_hgb_daily_topk_classifier.py

test-btcusdc-v104:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v104_daily_topk_probability_ledger_selects_confident_non_overlapping_predictions tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v104_gate_requires_profit_win_frequency_and_months

btcusdc-selector-locked-v104-audit-v105:
	PYTHONPATH=src python scripts/run_btcusdc_v105_selector_locked_v104_audit.py

test-btcusdc-v105:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v105_selector_locked_decision_ignores_holdout_ranking tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v105_selector_gate_uses_selector_fields_only

btcusdc-exact-daily-coverage-classifier-v106:
	PYTHONPATH=src python scripts/run_btcusdc_v106_exact_daily_coverage_classifier.py

test-btcusdc-v106:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v106_exact_daily_gate_requires_every_calendar_day tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v106_selector_locked_exact_daily_decision_uses_selector_only

btcusdc-price-context-exact-daily-classifier-v107:
	PYTHONPATH=src python scripts/run_btcusdc_v107_price_context_exact_daily_classifier.py

test-btcusdc-v107:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v107_price_context_features_use_prior_high_low_without_lookahead tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v107_feature_frame_includes_price_context_columns

btcusdc-technical-indicator-exact-daily-classifier-v108:
	PYTHONPATH=src python scripts/run_btcusdc_v108_technical_indicator_exact_daily_classifier.py

test-btcusdc-v108:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v108_technical_indicators_use_prior_bars_without_lookahead tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v108_feature_frame_includes_technical_indicator_columns

btcusdc-feature-family-ensemble-exact-daily-v109:
	PYTHONPATH=src python scripts/run_btcusdc_v109_feature_family_ensemble_exact_daily.py

test-btcusdc-v109:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v109_average_probability_frames_aligns_by_timestamp

btcusdc-flow-sweep-regime-ensemble-v110:
	PYTHONPATH=src python scripts/run_btcusdc_v110_flow_sweep_regime_ensemble.py

test-btcusdc-v110:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v110_flow_sweep_regime_features_use_prior_bars_without_lookahead tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v110_feature_frame_includes_flow_sweep_regime_columns tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v110_average_probability_frames_reuses_timestamp_alignment

btcusdc-high-confidence-daily-fallback-v111:
	PYTHONPATH=src python scripts/run_btcusdc_v111_high_confidence_daily_fallback.py

test-btcusdc-v111:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v111_daily_fallback_fills_missing_days_without_filling_to_topk tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v111_selector_decision_allows_nonzero_floor_when_fallback_is_exact_daily

btcusdc-expanded-topk-daily-fallback-v112:
	PYTHONPATH=src python scripts/run_btcusdc_v112_expanded_topk_daily_fallback.py

test-btcusdc-v112:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v112_performance_target_requires_five_percent_improvement tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v112_selector_decision_uses_selector_only_before_target_check

btcusdc-v112-earliest-walk-forward-v113:
	PYTHONPATH=src python scripts/run_btcusdc_v113_v112_earliest_walk_forward.py

test-btcusdc-v113:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v113_fold_windows_use_warmup_and_cover_latest_available_data

btcusdc-v112-guard-sweep-v114:
	PYTHONPATH=src python scripts/run_btcusdc_v114_v112_guard_sweep.py

test-btcusdc-v114:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v114_candidate_summary_requires_target_improvement_and_other_month_guard

btcusdc-v112-contrarian-sizing-v115:
	PYTHONPATH=src python scripts/run_btcusdc_v115_v112_contrarian_sizing.py

test-btcusdc-v115:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v115_contrarian_sizing_downweights_trend_following_signals tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v115_sizing_summary_requires_five_percent_and_month_guard

btcusdc-v115-forward-monitoring-v116:
	PYTHONPATH=src python scripts/run_btcusdc_v116_v115_forward_monitoring.py

test-btcusdc-v116:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v116_monitoring_decision_separates_no_data_from_no_signal

btcusdc-v115-live-feasibility-v118:
	PYTHONPATH=src python scripts/run_btcusdc_v118_live_executable_feasibility.py

test-btcusdc-v118:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v118_live_non_overlapping_indices_are_chronological tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v118_similarity_gate_requires_v115_like_performance

btcusdc-v115-live-entry-model-audit-v119:
	PYTHONPATH=src python scripts/run_btcusdc_v119_live_entry_model_audit.py

test-btcusdc-v119:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v119_similarity_gate_requires_v115_like_performance

btcusdc-v115-live-peak-trigger-scan-v120:
	PYTHONPATH=src python scripts/run_btcusdc_v120_live_peak_trigger_scan.py

test-btcusdc-v120:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v120_live_non_overlapping_indices_are_chronological tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v120_similarity_gate_requires_v115_like_performance

btcusdc-v115-live-native-entry-model-v121:
	PYTHONPATH=src python scripts/run_btcusdc_v121_live_native_entry_model.py

test-btcusdc-v121:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v121_live_native_target_uses_current_trade_pnl_threshold tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v121_prior_fold_training_indices_use_no_current_or_future_rows tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v121_similarity_gate_requires_v115_like_performance

btcusdc-v115-live-drought-fallback-v122:
	PYTHONPATH=src python scripts/run_btcusdc_v122_live_drought_fallback.py

test-btcusdc-v122:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v122_drought_fallback_waits_for_no_recent_trade tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v122_similarity_gate_requires_v115_like_performance

btcusdc-v115-live-hourly-threshold-scan-v123:
	PYTHONPATH=src python scripts/run_btcusdc_v123_live_hourly_threshold_scan.py

test-btcusdc-v123:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v123_group_thresholds_use_prior_folds_only tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v123_similarity_gate_requires_v115_like_performance

btcusdc-v115-live-family-ensemble-v124:
	PYTHONPATH=src python scripts/run_btcusdc_v124_live_family_ensemble.py

test-btcusdc-v124:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v124_priority_ensemble_prefers_higher_priority_same_time tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v124_similarity_gate_requires_v115_like_performance

btcusdc-v115-live-prior-day-topk-cutoff-v125:
	PYTHONPATH=src python scripts/run_btcusdc_v125_live_prior_day_topk_cutoff.py

test-btcusdc-v125:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v125_daily_cutoff_uses_prior_days_only tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v125_similarity_gate_requires_v115_like_performance

btcusdc-v115-live-family-ensemble-prior-day-cutoff-v126:
	PYTHONPATH=src python scripts/run_btcusdc_v126_live_family_ensemble_with_prior_day_cutoff.py

test-btcusdc-v126:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v126_prior_day_cutoff_source_uses_only_prior_days tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v126_similarity_gate_requires_v115_like_performance

btcusdc-v115-live-source-adaptive-sizing-v127:
	PYTHONPATH=src python scripts/run_btcusdc_v127_live_source_adaptive_sizing.py

test-btcusdc-v127:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v127_source_adaptive_sizing_uses_prior_source_outcomes_only tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v127_similarity_gate_requires_v115_like_performance

btcusdc-v115-live-source-health-sizing-v128:
	PYTHONPATH=src python scripts/run_btcusdc_v128_live_source_health_sizing.py

test-btcusdc-v128:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v128_source_health_gate_uses_prior_source_outcomes_only tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v128_similarity_gate_requires_v115_like_performance

btcusdc-v115-live-short-cooldown-source-sizing-v129:
	PYTHONPATH=src python scripts/run_btcusdc_v129_live_short_cooldown_source_sizing.py

test-btcusdc-v129:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v129_deduped_priority_events_keep_one_per_timestamp_before_cooldown tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v129_similarity_gate_requires_v115_like_performance

btcusdc-v115-live-consensus-confidence-sizing-v130:
	PYTHONPATH=src python scripts/run_btcusdc_v130_live_consensus_confidence_sizing.py

test-btcusdc-v130:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v130_consensus_features_use_same_timestamp_only tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v130_best_trades_keeps_consensus_config_names tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v130_similarity_gate_requires_v115_like_performance

btcusdc-v115-live-probability-floor-rescue-v131:
	PYTHONPATH=src python scripts/run_btcusdc_v131_live_probability_floor_rescue.py

test-btcusdc-v131:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v131_probability_floor_events_are_chronological_without_daily_cap tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v131_probability_config_uses_named_cooldown tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v131_similarity_gate_requires_v115_like_performance

btcusdc-v115-live-additive-rescue-hour-veto-v132:
	PYTHONPATH=src python scripts/run_btcusdc_v132_live_additive_rescue_hour_veto.py

test-btcusdc-v132:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v132_additive_rescue_keeps_base_pnl_and_allows_same_timestamp tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v132_hour_veto_uses_current_timestamp_hour_only tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v132_similarity_gate_requires_v115_like_performance

btcusdc-v115-live-rescue-weight-step-v133:
	PYTHONPATH=src python scripts/run_btcusdc_v133_live_rescue_weight_step.py

test-btcusdc-v133:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v133_config_keeps_live_execution_constraints tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v133_improvement_gate_requires_five_percent_over_v132 tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v133_summary_records_no_daily_cap_or_day_end_ranking

btcusdc-v115-live-weight-hour-step-v134:
	PYTHONPATH=src python scripts/run_btcusdc_v134_live_weight_hour_step.py

test-btcusdc-v134:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v134_config_keeps_live_execution_constraints tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v134_improvement_gate_requires_ten_percent_over_v133 tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v134_summary_records_no_daily_cap_or_day_end_ranking

btcusdc-v115-live-drawdown-guard-v135:
	PYTHONPATH=src python scripts/run_btcusdc_v135_live_drawdown_guard.py

test-btcusdc-v135:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v135_config_records_drawdown_reduction_target tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v135_drawdown_guard_pauses_until_next_utc_day_after_realized_loss tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v135_gate_requires_half_drawdown_and_profit_floor

btcusdc-v115-live-win-rate-guard-v136:
	PYTHONPATH=src python scripts/run_btcusdc_v136_live_win_rate_guard.py

test-btcusdc-v136:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v136_config_keeps_live_constraints_and_no_degrade_targets tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v136_hour17_guard_keeps_consensus2_and_high_prior_v1257 tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v136_gate_requires_win_rate_and_no_v135_degrade

btcusdc-v115-live-weighted-model-ensemble-v137:
	PYTHONPATH=src python scripts/run_btcusdc_v137_live_weighted_model_ensemble.py

test-btcusdc-v137:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v137_config_uses_weighted_model_ensemble_without_new_limits tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v137_weighted_average_probability_frames_uses_family_weights tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v137_gate_requires_model_improvement_without_v135_degrade

btcusdc-v115-live-confidence-sized-model-v138:
	PYTHONPATH=src python scripts/run_btcusdc_v138_live_confidence_sized_model.py

test-btcusdc-v138:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v138_config_uses_confidence_sizing_without_new_trade_limits tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v138_confidence_sizing_changes_weight_without_filtering_events tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v138_gate_requires_v137_profit_improvement_without_core_degrade

btcusdc-v139-indicator-leverage:
	PYTHONPATH=src python scripts/run_btcusdc_v139_indicator_leverage.py

test-btcusdc-v139:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v139_config_uses_indicator_leverage_without_filtering_trades tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v139_indicator_keys_classify_rescue_confidence_and_base_source tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v139_indicator_leverage_increases_account_pnl_without_changing_trade_count

btcusdc-v140-performance-leverage:
	PYTHONPATH=src python scripts/run_btcusdc_v140_performance_leverage.py

test-btcusdc-v140:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v140_config_promotes_fixed_3x_performance_overlay tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v140_fixed_leverage_scales_account_path_without_changing_trades tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v140_gate_requires_significant_v139_improvement_and_drawdown_cap

btcusdc-v141-drawdown-throttle-leverage:
	PYTHONPATH=src python scripts/run_btcusdc_v141_drawdown_throttle_leverage.py

test-btcusdc-v141:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v141_config_uses_causal_drawdown_throttle tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v141_throttle_uses_prior_drawdown_before_current_trade tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v141_gate_requires_high_profit_and_lower_drawdown_than_v140

btcusdc-v142-high-confidence-rescue-5x:
	PYTHONPATH=src python scripts/run_btcusdc_v142_high_confidence_rescue_5x.py

test-btcusdc-v142:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v142_config_applies_5x_only_to_high_confidence_rescue tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v142_high_confidence_5x_is_disabled_after_drawdown_trigger tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v142_gate_requires_no_v141_drawdown_degradation_and_profit_gain

btcusdc-v143-market-emotion-trend-audit:
	PYTHONPATH=src python scripts/run_btcusdc_v143_market_emotion_trend_audit.py

test-btcusdc-v143:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v143_market_emotion_trend_audit.py

btcusdc-v144-funding-sentiment-governor:
	PYTHONPATH=src python scripts/run_btcusdc_v144_funding_sentiment_governor.py

test-btcusdc-v144:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v144_funding_sentiment_governor.py

btcusdc-v145-derivatives-sentiment-monitor:
	PYTHONPATH=src python scripts/run_btcusdc_v145_derivatives_sentiment_monitor.py

test-btcusdc-v145:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v145_derivatives_sentiment_monitor.py

btcusdc-v146-fear-greed-macro-overlay:
	PYTHONPATH=src python scripts/run_btcusdc_v146_fear_greed_macro_overlay.py

test-btcusdc-v146:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v146_fear_greed_macro_overlay.py

btcusdc-v147-fear-greed-regime-risk-overlay:
	PYTHONPATH=src python scripts/run_btcusdc_v147_fear_greed_regime_risk_overlay.py

test-btcusdc-v147:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v147_fear_greed_regime_risk_overlay.py

btcusdc-v148-premium-basis-sentiment-overlay:
	PYTHONPATH=src python scripts/run_btcusdc_v148_premium_basis_sentiment_overlay.py

test-btcusdc-v148:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v148_premium_basis_sentiment_overlay.py

btcusdc-v149-confidence-persistence-overlay:
	PYTHONPATH=src python scripts/run_btcusdc_v149_confidence_persistence_overlay.py

test-btcusdc-v149:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v149_confidence_persistence_overlay.py

btcusdc-v150-funding-persistence-overlay:
	PYTHONPATH=src python scripts/run_btcusdc_v150_funding_persistence_overlay.py

test-btcusdc-v150:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v150_funding_persistence_overlay.py

btcusdc-v151-range-alignment-overlay:
	PYTHONPATH=src python scripts/run_btcusdc_v151_range_alignment_overlay.py

test-btcusdc-v151:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v151_range_alignment_overlay.py

btcusdc-v152-short-trend-activity-overlay:
	PYTHONPATH=src python scripts/run_btcusdc_v152_short_trend_activity_overlay.py

test-btcusdc-v152:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v152_short_trend_activity_overlay.py

btcusdc-v153-premium-balance-overlay:
	PYTHONPATH=src python scripts/run_btcusdc_v153_premium_balance_overlay.py

test-btcusdc-v153:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v153_premium_balance_overlay.py

btcusdc-v154-rescue-funding-stabilizer:
	PYTHONPATH=src python scripts/run_btcusdc_v154_rescue_funding_stabilizer.py

test-btcusdc-v154:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v154_rescue_funding_stabilizer.py

btcusdc-v155-base-long-premium-expansion:
	PYTHONPATH=src python scripts/run_btcusdc_v155_base_long_premium_expansion.py

test-btcusdc-v155:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v155_base_long_premium_expansion.py

btcusdc-v156-base-long-premium-stepup:
	PYTHONPATH=src python scripts/run_btcusdc_v156_base_long_premium_stepup.py

test-btcusdc-v156:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v156_base_long_premium_stepup.py

btcusdc-v157-market-condition-post-stepup-audit:
	PYTHONPATH=src python scripts/run_btcusdc_v157_market_condition_post_stepup_audit.py

test-btcusdc-v157:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v157_market_condition_post_stepup_audit.py

btcusdc-v158-base-range-position-boost:
	PYTHONPATH=src python scripts/run_btcusdc_v158_base_range_position_boost.py

test-btcusdc-v158:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v158_base_range_position_boost.py

btcusdc-v159-base-trend-abs-boost:
	PYTHONPATH=src python scripts/run_btcusdc_v159_base_trend_abs_boost.py

test-btcusdc-v159:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v159_base_trend_abs_boost.py

btcusdc-v160-base-trend-abs-stepup:
	PYTHONPATH=src python scripts/run_btcusdc_v160_base_trend_abs_stepup.py

test-btcusdc-v160:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v160_base_trend_abs_stepup.py

btcusdc-v161-day-sofar-count-boost:
	PYTHONPATH=src python scripts/run_btcusdc_v161_day_sofar_count_boost.py

test-btcusdc-v161:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v161_day_sofar_count_boost.py

btcusdc-v162-long-trend-follow-boost:
	PYTHONPATH=src python scripts/run_btcusdc_v162_long_trend_follow_boost.py

test-btcusdc-v162:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v162_long_trend_follow_boost.py

btcusdc-v163-post-v162-candidate-audit:
	PYTHONPATH=src python scripts/run_btcusdc_v163_post_v162_candidate_audit.py

test-btcusdc-v163:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v163_post_v162_candidate_audit.py

btcusdc-v164-v162-robustness-audit:
	PYTHONPATH=src python scripts/run_btcusdc_v164_v162_robustness_audit.py

test-btcusdc-v164:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v164_v162_robustness_audit.py

btcusdc-v165-cost-fragility-audit:
	PYTHONPATH=src python scripts/run_btcusdc_v165_cost_fragility_audit.py

test-btcusdc-v165:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v165_cost_fragility_audit.py

btcusdc-v166-execution-budget-audit:
	PYTHONPATH=src python scripts/run_btcusdc_v166_execution_budget_audit.py

test-btcusdc-v166:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v166_execution_budget_audit.py

btcusdc-v167-market-condition-role-audit:
	PYTHONPATH=src python scripts/run_btcusdc_v167_market_condition_role_audit.py

test-btcusdc-v167:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v167_market_condition_role_audit.py

btcusdc-v168-execution-readiness-gate:
	PYTHONPATH=src python scripts/run_btcusdc_v168_execution_readiness_gate.py

test-btcusdc-v168:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v168_execution_readiness_gate.py

btcusdc-v169-fragile-execution-profile:
	PYTHONPATH=src python scripts/run_btcusdc_v169_fragile_execution_profile.py

test-btcusdc-v169:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v169_fragile_execution_profile.py

btcusdc-v170-execution-aware-risk-control:
	PYTHONPATH=src python scripts/run_btcusdc_v170_execution_aware_risk_control.py

test-btcusdc-v170:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v170_execution_aware_risk_control.py

btcusdc-v171-max-drawdown-source-audit:
	PYTHONPATH=src python scripts/run_btcusdc_v171_max_drawdown_source_audit.py

test-btcusdc-v171:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v171_max_drawdown_source_audit.py

btcusdc-v172-rescue-cluster-guard:
	PYTHONPATH=src python scripts/run_btcusdc_v172_rescue_cluster_guard.py

test-btcusdc-v172:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v172_rescue_cluster_guard.py

btcusdc-v173-timestamp-side-exposure-cap:
	PYTHONPATH=src python scripts/run_btcusdc_v173_timestamp_side_exposure_cap.py

test-btcusdc-v173:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v173_timestamp_side_exposure_cap.py

btcusdc-v174-long-rescue-state-audit:
	PYTHONPATH=src python scripts/run_btcusdc_v174_long_rescue_state_audit.py

test-btcusdc-v174:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v174_long_rescue_state_audit.py

btcusdc-v175-long-rescue-state-overlay:
	PYTHONPATH=src python scripts/run_btcusdc_v175_long_rescue_state_overlay.py

test-btcusdc-v175:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_v175_long_rescue_state_overlay.py

paper-trade-v142-demo:
	PYTHONPATH=src python -m lob_microprice_lab.cli paper-trade-v142 --out runs/paper_v142_demo --source synthetic --ticks 5 --interval-sec 60 --clean --no-sleep

test-paper-trading-v142:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_paper_trading_v142.py

trade-replay-v142-page:
	PYTHONPATH=src python -m lob_microprice_lab.cli trade-replay-v142 --out runs/v142_trading_replay/index.html --start 2024-07-01 --end 2026-06-12 --initial-balance-usdc 10000 --signal-reference runs/research_v119_btcusdc_live_entry_model/v119_live_feature_frame.csv

test-trade-replay-v142:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_trade_replay_page_v142.py
