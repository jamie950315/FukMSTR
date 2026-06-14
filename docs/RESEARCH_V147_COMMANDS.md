# Research V147 Commands

V147 tests whether the Fear & Greed regime buckets can be used as downside-only risk overlays on top of the V144/V146 account path.

The scan focuses on reducing exposure in specific sentiment regimes rather than adding exposure. The 2026 holdout is not used for candidate selection.

## Run

```bash
make btcusdc-v147-fear-greed-regime-risk-overlay
```

## Focused Test

```bash
make test-btcusdc-v147
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

Generated local outputs are written under:

```text
runs/research_v147_fear_greed_regime_risk_overlay/
```

The committed report is:

```text
reports/RESEARCH_V147_BTCUSDC_FEAR_GREED_REGIME_RISK_OVERLAY.md
```
