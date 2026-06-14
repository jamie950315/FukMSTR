# V99 Low Cost Execution Headroom Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure whether the V97/V98 high-frequency BTCUSDC candidates can satisfy win rate above 55%, at least one trade per day, stable positive selector/holdout returns, and any realistic nonzero execution cost.

**Architecture:** Reuse the V97 HGB candidate grid and V98 gross-ledger replay. Add a finer cost sweep from 0 to 4 bps and summarize each base policy's maximum passing fee, so zero-fee-only candidates are separated from candidates with actual execution headroom.

**Tech Stack:** Python, pandas, sklearn, pytest, Makefile.

---

### Task 1: V99 Tests

**Files:**
- Modify: `tests/test_btcusdc_independent_validation_v27.py`

- [ ] **Step 1: Write failing tests**

Add tests that import `scripts/run_btcusdc_v99_low_cost_headroom.py` and verify:
- `_policy_headroom()` returns the maximum fee where a base policy passes.
- `_decision_from_headroom()` refuses to mark the goal satisfied when every passing row is zero-fee-only.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v99_policy_headroom_uses_max_passing_fee tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v99_decision_requires_nonzero_fee_headroom
```

Expected: FAIL because the V99 script does not exist yet.

### Task 2: V99 Runner

**Files:**
- Create: `scripts/run_btcusdc_v99_low_cost_headroom.py`
- Modify: `Makefile`
- Create: `docs/RESEARCH_V99_COMMANDS.md`

- [ ] **Step 1: Implement the minimal V99 runner**

Reuse V98 fee replay logic with fee scenarios:

```python
FEE_SCENARIOS_BPS = (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0)
```

Write:
- `runs/research_v99_btcusdc_low_cost_headroom/v99_low_cost_candidates.csv`
- `runs/research_v99_btcusdc_low_cost_headroom/v99_low_cost_passed_candidates.csv`
- `runs/research_v99_btcusdc_low_cost_headroom/v99_policy_headroom.csv`
- `runs/research_v99_btcusdc_low_cost_headroom/v99_summary.json`
- `reports/RESEARCH_V99_BTCUSDC_LOW_COST_HEADROOM_RESULTS.md`

- [ ] **Step 2: Add Makefile targets**

Add:

```make
btcusdc-low-cost-headroom-v99:
	PYTHONPATH=src python scripts/run_btcusdc_v99_low_cost_headroom.py

test-btcusdc-v99:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v99_policy_headroom_uses_max_passing_fee tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v99_decision_requires_nonzero_fee_headroom
```

- [ ] **Step 3: Run targeted tests**

Run:

```bash
make test-btcusdc-v99
```

Expected: PASS.

### Task 3: V99 Research Run And Verification

**Files:**
- Generated: `runs/research_v99_btcusdc_low_cost_headroom/*`
- Generated: `reports/RESEARCH_V99_BTCUSDC_LOW_COST_HEADROOM_RESULTS.md`

- [ ] **Step 1: Run V99**

Run:

```bash
make btcusdc-low-cost-headroom-v99
```

Expected: JSON summary printed with selected policy, passing counts, and maximum passing nonzero fee.

- [ ] **Step 2: Run full verification**

Run:

```bash
make test-btcusdc-v99
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

Expected: all commands exit 0.

- [ ] **Step 3: Interpret result**

Report whether the high-frequency goal is satisfied. If the maximum passing fee is 0 bps only, leave the active goal incomplete. If a nonzero fee passes, clearly state the allowed cost ceiling and that it still requires live maker-fill monitoring.
