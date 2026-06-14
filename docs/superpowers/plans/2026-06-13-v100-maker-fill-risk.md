# V100 Maker Fill Risk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test whether the V99 near-zero-cost high-frequency BTCUSDC candidate still satisfies the target after maker-style missed fills and adverse selection.

**Architecture:** Load the V99 passing ledgers, replay each candidate under deterministic fill-rate stress and adverse-selection fill stress, then evaluate the same selector/holdout quality gate. The decision only treats the route as maker-viable if every required execution-stress row remains positive, above 55% win rate, and above one trade per day.

**Tech Stack:** Python, pandas, pytest, Makefile.

---

### Task 1: V100 Tests

**Files:**
- Modify: `tests/test_btcusdc_independent_validation_v27.py`

- [ ] **Step 1: Write failing tests**

Add tests that import `scripts/run_btcusdc_v100_maker_fill_risk.py` and verify:
- `_stress_ledger()` with `adverse_selection` keeps the worst trades first and deducts extra adverse cost.
- `_decision_from_stress()` rejects a candidate when any required stress row fails, even if baseline passes.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v100_adverse_fill_keeps_worst_trades_and_extra_cost tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v100_decision_requires_all_required_stresses_to_pass
```

Expected: FAIL because the V100 script does not exist yet.

### Task 2: V100 Runner

**Files:**
- Create: `scripts/run_btcusdc_v100_maker_fill_risk.py`
- Modify: `Makefile`
- Create: `docs/RESEARCH_V100_COMMANDS.md`

- [ ] **Step 1: Implement maker fill stress**

Use V99 passing ledgers. Stress dimensions:

```python
FILL_MODELS = ("time_stride", "adverse_selection")
FILL_RATES = (1.0, 0.95, 0.9, 0.8, 0.7)
EXTRA_ADVERSE_BPS = (0.0, 0.125, 0.25, 0.5)
```

Required stress contract:

```python
REQUIRED_FILL_MODELS = ("time_stride", "adverse_selection")
REQUIRED_MIN_FILL_RATE = 0.9
REQUIRED_MAX_EXTRA_ADVERSE_BPS = 0.25
```

- [ ] **Step 2: Add outputs**

Write:
- `runs/research_v100_btcusdc_maker_fill_risk/v100_maker_fill_stress.csv`
- `runs/research_v100_btcusdc_maker_fill_risk/v100_summary.json`
- `reports/RESEARCH_V100_BTCUSDC_MAKER_FILL_RISK_RESULTS.md`

- [ ] **Step 3: Add Makefile targets**

Add:

```make
btcusdc-maker-fill-risk-v100:
	PYTHONPATH=src python scripts/run_btcusdc_v100_maker_fill_risk.py

test-btcusdc-v100:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v100_adverse_fill_keeps_worst_trades_and_extra_cost tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v100_decision_requires_all_required_stresses_to_pass
```

### Task 3: Run And Verify

**Files:**
- Generated: `runs/research_v100_btcusdc_maker_fill_risk/*`
- Generated: `reports/RESEARCH_V100_BTCUSDC_MAKER_FILL_RISK_RESULTS.md`

- [ ] **Step 1: Run V100**

Run:

```bash
make btcusdc-maker-fill-risk-v100
```

- [ ] **Step 2: Run verification**

Run:

```bash
make test-btcusdc-v100
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

- [ ] **Step 3: Interpret**

If V100 fails required maker stress, keep the goal active and state that V99 remains a near-zero-cost research candidate, not a verified executable high-frequency strategy.
