# Research V68 Fixed Flow Stability Commands

## Purpose

V68 audits a fixed BTCUSDC aggTrade-flow policy instead of selecting a candidate from validation outcomes. It starts from the strongest V50 fixed-policy family and checks full-period, chronological-fold, entry-delay, and extra-cost robustness.

## Run

```bash
make btcusdc-fixed-flow-stability-v68
```

## Targeted Test

```bash
make test-btcusdc-v68
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

- `runs/research_v68_btcusdc_fixed_flow_stability/v68_summary.json`
- `runs/research_v68_btcusdc_fixed_flow_stability/v68_base_trade_ledger.csv`
- `runs/research_v68_btcusdc_fixed_flow_stability/v68_fold_summary.csv`
- `runs/research_v68_btcusdc_fixed_flow_stability/v68_delay_summary.csv`
- `runs/research_v68_btcusdc_fixed_flow_stability/v68_extra_cost_summary.csv`
- `reports/RESEARCH_V68_FIXED_FLOW_STABILITY_RESULTS.md`

## Pass Standard

The fixed policy must be positive after fees, have enough trades, keep most chronological folds positive, avoid a large worst-fold loss, stay positive under entry-delay stress, and keep the 0 bps and 4 bps extra-cost cases positive.
