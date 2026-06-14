# Research V67 Sparse TP Route Closure Commands

## Purpose

V67 closes the BTCUSDC sparse take-profit route by consolidating the true BTCUSDC public replay, V60 design selector, V64 dense delay scan, V65 signal fragility audit, and V66 design-robust selector results.

The route is not promoted unless all of these are true:

- The true BTCUSDC replay gate passes.
- The V60 design-selected holdout passes every dense delay.
- The V66 design-robust selected rule passes every holdout dense delay.

## Run

```bash
make btcusdc-sparse-tp-route-closure-v67
```

## Targeted Test

```bash
make test-btcusdc-v67
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Expected Outputs

- `runs/research_v67_btcusdc_sparse_tp_route_closure/v67_summary.json`
- `runs/research_v67_btcusdc_sparse_tp_route_closure/v67_sparse_tp_route_decision.csv`
- `reports/RESEARCH_V67_SPARSE_TP_ROUTE_CLOSURE.md`

## Expected Decision

The expected decision is `promote_sparse_tp=false`.

Primary rejection reasons:

- `true_btcusdc_replay_failed`
- `v60_dense_holdout_not_fully_robust`
- `design_robust_selector_failed_holdout`
