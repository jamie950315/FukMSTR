# V101 Thick Edge Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Search for a BTCUSDC high-frequency candidate with thicker predicted edge that can pass the target under the existing 8.5 bps round-trip cost assumption.

**Architecture:** Reuse the existing BTCUSDC 1m feature frame, but replace probability classification with return-magnitude regression. Trade only when predicted future return magnitude exceeds a fixed edge threshold, then evaluate selector and holdout with the same win-rate, daily-frequency, positive-return, and monthly-stability gate.

**Tech Stack:** Python, pandas, sklearn HistGradientBoostingRegressor, pytest, Makefile.

---

### Task 1: V101 Tests

**Files:**
- Modify: `tests/test_btcusdc_independent_validation_v27.py`

- [ ] **Step 1: Write failing tests**

Add tests that import `scripts/run_btcusdc_v101_thick_edge_regression.py` and verify:
- `_edge_prediction_ledger()` takes long trades for positive predictions above threshold and short trades for negative predictions below threshold, with non-overlap spacing and 8.5 bps fee deduction.
- `_passes_thick_edge_gate()` requires selector and holdout positive return, win rate above 55%, at least one trade per day, and positive month rate above 50%.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v101_edge_prediction_ledger_uses_signed_edge_and_spacing tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v101_gate_requires_profit_win_frequency_and_months
```

Expected: FAIL because the V101 script does not exist yet.

### Task 2: V101 Runner

**Files:**
- Create: `scripts/run_btcusdc_v101_thick_edge_regression.py`
- Modify: `Makefile`
- Create: `docs/RESEARCH_V101_COMMANDS.md`

- [ ] **Step 1: Implement regression scan**

Use:

```python
HORIZONS = (15, 30, 60, 120)
EDGE_THRESHOLDS_BPS = (8.5, 10.0, 12.5, 15.0, 20.0, 25.0, 30.0, 40.0)
FEE_BPS = 8.5
```

Train only before the selector window. Evaluate thresholds on selector and holdout. Do not tune on holdout.

- [ ] **Step 2: Add outputs**

Write:
- `runs/research_v101_btcusdc_thick_edge_regression/v101_thick_edge_candidates.csv`
- `runs/research_v101_btcusdc_thick_edge_regression/v101_thick_edge_passed_candidates.csv`
- `runs/research_v101_btcusdc_thick_edge_regression/v101_summary.json`
- `reports/RESEARCH_V101_BTCUSDC_THICK_EDGE_REGRESSION_RESULTS.md`

- [ ] **Step 3: Add Makefile targets**

Add:

```make
btcusdc-thick-edge-regression-v101:
	PYTHONPATH=src python scripts/run_btcusdc_v101_thick_edge_regression.py

test-btcusdc-v101:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v101_edge_prediction_ledger_uses_signed_edge_and_spacing tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v101_gate_requires_profit_win_frequency_and_months
```

### Task 3: Run And Verify

**Files:**
- Generated: `runs/research_v101_btcusdc_thick_edge_regression/*`
- Generated: `reports/RESEARCH_V101_BTCUSDC_THICK_EDGE_REGRESSION_RESULTS.md`

- [ ] **Step 1: Run V101**

Run:

```bash
make btcusdc-thick-edge-regression-v101
```

- [ ] **Step 2: Run verification**

Run:

```bash
make test-btcusdc-v101
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

- [ ] **Step 3: Interpret**

If no candidate passes under 8.5 bps cost, state that the current complete 1m public-data feature set still has no verified daily high-frequency strategy and the next path needs a stronger data source.
