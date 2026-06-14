# Research V40 Commands

V40 tests whether equal-weight top-K candidate portfolios reduce BTCUSDC selector error compared with selecting one candidate.

```bash
make btcusdc-topk-portfolio-v40
make test-btcusdc-v40
PYTHONPATH=src python -m py_compile src/lob_microprice_lab/*.py scripts/run_btcusdc_topk_portfolio_v40.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
```

Inputs:

```text
runs/research_v36_btcusdc_aggtrade_flow_ytd_rolling/btcusdc_v28_candidate_evaluations.csv
runs/research_v29_btcusdc_ytd_rolling_broad_probe/btcusdc_v28_candidate_evaluations.csv
```

Outputs:

```text
runs/research_v40_btcusdc_topk_portfolio/summary_v40.json
runs/research_v40_btcusdc_topk_portfolio/REPORT_V40.md
```
