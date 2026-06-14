# Research V08 Commands

Run from the project root with `PYTHONPATH=src`.

## Strict fixed-template audit

This is the primary V08 command pattern.  It chooses the candidate from source calibration ranking only.

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli fixed-template-audit \
  --ensemble-dir runs/research_v07_long_sweep_stationary_logistic/h90p0_thr1p0_top80_logistic \
  --out runs/local_v08_h90_source_rank \
  --horizon-sec 90 \
  --cost-bps 1.5 \
  --latency-sec 0.5 \
  --edge-thresholds 0.1,0.2,0.3,0.5,0.7 \
  --signed-columns imbalance_l3,microprice_dev_bps_l3,mid_ret_60r_bps \
  --spread-quantiles 1.0 \
  --vol-modes none \
  --template-source first_fold \
  --selection-policy source_rank \
  --min-source-trades 8 \
  --top-k-templates 80 \
  --stress-cost-bps-values 1.5,3.0,5.0 \
  --stress-latency-sec-values 0,0.5,1.0,2.0 \
  --clean
```

## Diagnostic validation-rank audit

This is useful for hypothesis generation.  It is data-snooped because it selects the best validation-ranked frozen template.

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli fixed-template-audit \
  --ensemble-dir runs/research_v07_long_sweep_stationary_logistic/h90p0_thr1p0_top80_logistic \
  --out runs/local_v08_h90_validation_rank \
  --horizon-sec 90 \
  --cost-bps 1.5 \
  --latency-sec 0.5 \
  --edge-thresholds 0.1,0.2,0.3,0.5,0.7 \
  --signed-columns imbalance_l3,microprice_dev_bps_l3,mid_ret_60r_bps \
  --spread-quantiles 1.0 \
  --vol-modes none \
  --template-source first_fold \
  --selection-policy validation_rank \
  --min-source-trades 8 \
  --top-k-templates 80 \
  --stress-cost-bps-values 1.5,3.0,5.0 \
  --stress-latency-sec-values 0,0.5,1.0,2.0 \
  --clean
```

## Trade audit

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli audit-trades \
  --backtest runs/research_v08_fixed_template_h90_validation_rank/selected_oof_backtest.csv \
  --out runs/local_v08_trade_audit_h90_validation_rank \
  --horizon-sec 90 \
  --latency-sec 0.5 \
  --clean
```

## Multi-horizon portfolio diagnostic

Strict source-rank portfolio:

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli combine-fixed-backtests \
  --backtests \
    runs/research_v08_fixed_template_h90_source_rank/selected_oof_backtest.csv \
    runs/research_v08_fixed_template_h120_source_rank/selected_oof_backtest.csv \
    runs/research_v08_fixed_template_h60_source_rank/selected_oof_backtest.csv \
    runs/research_v08_fixed_template_h45_source_rank/selected_oof_backtest.csv \
  --horizons-sec 90,120,60,45 \
  --strategy-names h90_source,h120_source,h60_source,h45_source \
  --out runs/local_v08_portfolio_source_rank \
  --clean
```

Diagnostic validation-rank portfolio:

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli combine-fixed-backtests \
  --backtests \
    runs/research_v08_fixed_template_h90_validation_rank/selected_oof_backtest.csv \
    runs/research_v08_fixed_template_h120_validation_rank/selected_oof_backtest.csv \
    runs/research_v08_fixed_template_h60_validation_rank/selected_oof_backtest.csv \
    runs/research_v08_fixed_template_h45_validation_rank/selected_oof_backtest.csv \
  --horizons-sec 90,120,60,45 \
  --strategy-names h90_oracle,h120_oracle,h60_oracle,h45_oracle \
  --out runs/local_v08_portfolio_validation_rank \
  --clean
```

## Rebuild summary CSVs

```bash
python - <<'PY'
import json, pandas as pd, pathlib
rows=[]
for policy in ['source_rank','validation_rank']:
    for H in [45,60,90,120]:
        j=json.load(open(f'runs/research_v08_fixed_template_h{H}_{policy}/summary.json'))
        a=j['aggregate']; g=j['gate']; sg=j['stress_gate']; sn=j['shift_null']
        rows.append({
            'horizon_sec':H,
            'selection_policy':policy,
            'gate_passed':g['passed'],
            'failed_checks':';'.join(g['failed_checks']),
            'oof_trades':a['oof_trades'],
            'oof_hit_rate':a['oof_hit_rate'],
            'oof_mean_net_pnl_bps':a['oof_mean_net_pnl_bps'],
            'oof_total_net_pnl_bps':a['oof_total_net_pnl_bps'],
            'fold_mean_net_pnl_bps_min':a['fold_mean_net_pnl_bps_min'],
            'fold_bootstrap_p05_min':a['fold_bootstrap_mean_p05_bps_min'],
            'stress_passed':sg['passed'],
            'shift_p_mean':sn.get('p_null_mean_ge_actual'),
        })
out=pathlib.Path('runs/research_v08_summary'); out.mkdir(exist_ok=True)
pd.DataFrame(rows).to_csv(out/'fixed_template_summary.csv', index=False)
PY
```
