# Research V146 Commands

V146 tests whether the Alternative.me Crypto Fear & Greed Index can improve the V144 BTCUSDC account path as a macro sentiment sizing overlay.

The experiment keeps V144 as the base strategy and only changes position sizing during extreme macro sentiment states. The 2026 holdout is not used for candidate selection.

## Run

```bash
make btcusdc-v146-fear-greed-macro-overlay
```

## Focused Test

```bash
make test-btcusdc-v146
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

Generated local outputs are written under:

```text
runs/research_v146_fear_greed_macro_overlay/
```

The committed report is:

```text
reports/RESEARCH_V146_BTCUSDC_FEAR_GREED_MACRO_OVERLAY.md
```

## Source

```text
https://api.alternative.me/fng/?limit=0&format=json
```
