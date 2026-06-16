# V210 Paper-Shadow Fill Capture Commands

V210 creates V205/V209-compatible paper-shadow fill evidence from realtime signals and market snapshots.
It does not place live orders, tune thresholds, change entries, change exits, or change leverage rules.

## Run With Public Binance Price

```bash
make btcusdc-v210-paper-shadow-fill-capture SIGNAL_CSV=/path/to/signals.csv TICKS=60 CAPTURE_ID=paper-shadow-YYYYMMDD
```

## Run With A Price CSV

```bash
make btcusdc-v210-paper-shadow-fill-capture SIGNAL_CSV=/path/to/signals.csv PRICE_CSV=/path/to/prices.csv TICKS=60 CAPTURE_ID=paper-shadow-YYYYMMDD
```

The signal CSV must contain at least:

- `timestamp`
- `side` or `signal`

Recommended signal columns:

- `signal_id`
- `symbol`
- `source`
- `leg`
- `direction_probability`
- `available_at`
- `horizon_minutes`

## Focused Test

```bash
make test-btcusdc-v210
```

## Follow-Up Gate Checks

```bash
make btcusdc-v205-execution-validation
make btcusdc-v209-execution-provenance-gate
make btcusdc-v204-real-money-readiness-gate
```

V210 writes the fill audit to:

- `runs/research_v205_execution_validation/fill_audit.csv`

If fewer than 30 valid shadow fills are captured, V205 remains blocked.
Synthetic market prices are not converted into valid fill evidence.

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

- `runs/research_v210_paper_shadow_fill_capture/v210_paper_shadow_fill_capture_summary.json`
- `runs/research_v205_execution_validation/fill_audit.csv`
- `reports/RESEARCH_V210_BTCUSDC_PAPER_SHADOW_FILL_CAPTURE.md`

The `runs/` outputs are local generated evidence and should not be committed.
