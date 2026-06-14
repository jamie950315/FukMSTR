# BTCUSDC Rolling Forward V28 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend BTCUSDC validation beyond the single V27 held-out window and verify whether the strategy can repeatedly exceed 50% account return on forward windows.

**Architecture:** Reuse `btcusdc_independent_validation.py` for candidate generation, non-overlapping trade ledgers, and metrics. Add a rolling-forward runner that selects candidates on each calibration window only, applies them to the following validation window, and writes fold-level pass/fail evidence.

**Tech Stack:** Python, pandas, pytest, Binance public USD-M 1m kline zip files.

---

### Task 1: Rolling Forward API

**Files:**
- Modify: `src/lob_microprice_lab/btcusdc_independent_validation.py`
- Modify: `tests/test_btcusdc_independent_validation_v27.py`

- [ ] **Step 1: Write failing test**

Add a test that builds six synthetic daily kline blocks, runs rolling forward with two folds, and asserts each fold has a selected candidate, non-empty validation trades, and an aggregate `all_validation_windows_target_passed` boolean.

- [ ] **Step 2: Verify red**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py
```

Expected: import or attribute failure for the missing rolling-forward function.

- [ ] **Step 3: Implement minimal API**

Add `run_btcusdc_rolling_forward_validation(...)` and helpers that:

- loads kline files once,
- slices by date windows,
- generates candidates from calibration only,
- selects by calibration metrics only,
- writes fold metrics, selected candidates, and validation trades,
- returns aggregate fold pass/fail counts.

- [ ] **Step 4: Verify green**

Run the same pytest command and confirm it passes.

### Task 2: Longer Data Runner

**Files:**
- Create: `scripts/run_btcusdc_rolling_forward_v28.py`
- Modify: `Makefile`

- [ ] **Step 1: Add script**

Create a script that downloads BTCUSDC public 1m kline files for a longer date range, then runs rolling forward validation.

- [ ] **Step 2: Add Makefile targets**

Add:

```make
btcusdc-rolling-forward-v28:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src python scripts/run_btcusdc_rolling_forward_v28.py

test-btcusdc-v28:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py tests/test_btcusdc_contract_lock_v26.py tests/test_btc_portfolio_risk_lock_v25.py
```

### Task 3: Verification And Reporting

**Files:**
- Create: `docs/RESEARCH_V28_COMMANDS.md`
- Create: `reports/RESEARCH_V28_RESULTS.md`
- Generated: `runs/research_v28_btcusdc_rolling_forward/`

- [ ] **Step 1: Run commands**

Run:

```bash
make btcusdc-rolling-forward-v28
make test-btcusdc-v28
PYTHONPATH=src python -m py_compile src/lob_microprice_lab/*.py scripts/run_btcusdc_rolling_forward_v28.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
```

- [ ] **Step 2: Document result**

Write the actual pass/fail status. If any forward window fails the 50% target, state that the full stability goal remains unproven and identify the weak windows.
