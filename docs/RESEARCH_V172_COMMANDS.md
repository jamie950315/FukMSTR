# Research V172 Commands

V172 tests causal same-side rescue-cluster guards on top of the V162 selected account path. It was motivated by V171, which found that the max drawdown was concentrated in a short long-rescue cluster. The guard only scales existing rescue trades when prior same-side rescue trades already occurred inside the configured lookback window.

## Focused Test

```bash
make test-btcusdc-v172
```

## Run V172 Audit

```bash
make btcusdc-v172-rescue-cluster-guard
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

```text
runs/research_v172_rescue_cluster_guard/v172_policy_comparison.csv
runs/research_v172_rescue_cluster_guard/v172_selected_guarded_profile.csv
runs/research_v172_rescue_cluster_guard/v172_baseline_max_drawdown.csv
runs/research_v172_rescue_cluster_guard/v172_selected_max_drawdown.csv
runs/research_v172_rescue_cluster_guard/v172_rescue_cluster_guard_summary.json
runs/research_v172_rescue_cluster_guard/*_path.csv
reports/RESEARCH_V172_BTCUSDC_RESCUE_CLUSTER_GUARD.md
```

## Research Notes

- Base trades: V162 selected account path.
- Guarded trades: rescue trades only.
- Cluster context is causal: only prior same-side rescue trades are counted.
- V172 does not add trades, change side, change threshold, or promote live trading.
- This is a research risk audit, not a live trading guarantee.
