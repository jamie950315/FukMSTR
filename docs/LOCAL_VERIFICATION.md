# Local verification

Recommended verification after unzip:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .[dev]
PYTHONPATH=src pytest -q
```

Fast syntax check:

```bash
python -m py_compile src/lob_microprice_lab/*.py
```

Smoke test on synthetic data:

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli generate-sample --out data/sample --rows 800 --depth 5
PYTHONPATH=src python -m lob_microprice_lab.cli train --book data/sample/book.csv --trades data/sample/trades.csv --config configs/example.yaml --out runs/sample_smoke
```

The final package was syntax-checked with `python -m py_compile src/lob_microprice_lab/*.py`. The test suite should be rerun on the local machine after extraction.
