# V106 Exact Daily Coverage Classifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify whether the V104 MA HGB classifier can satisfy the strict interpretation of the goal: every calendar day must have at least one trade, while win rate stays above 55% and net profit remains positive.

**Architecture:** Reuse V104 classifier predictions and daily top-k ledger logic. Scan lower probability floors including `0.0` so each day can receive at least one trade, then require `active_day_count == calendar_day_count` for selector and holdout before applying the existing profit, win-rate, and month-stability gates.

**Tech Stack:** Python, pandas, scikit-learn, pytest, Makefile.

---

### Task 1: Exact Daily Gate Contract

**Files:**
- Modify: `tests/test_btcusdc_independent_validation_v27.py`
- Create: `scripts/run_btcusdc_v106_exact_daily_coverage_classifier.py`

- [ ] **Step 1: Write the failing tests**

Add tests that import V106 and verify:
- `_passes_exact_daily_gate()` requires selector and holdout active day counts to equal calendar day counts.
- `_selector_locked_exact_daily_decision()` selects using selector metrics only among exact-daily selector candidates.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v106_exact_daily_gate_requires_every_calendar_day tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v106_selector_locked_exact_daily_decision_uses_selector_only
```

Expected: FAIL because `scripts/run_btcusdc_v106_exact_daily_coverage_classifier.py` does not exist yet.

### Task 2: V106 Script and Commands

**Files:**
- Create: `scripts/run_btcusdc_v106_exact_daily_coverage_classifier.py`
- Create: `docs/RESEARCH_V106_COMMANDS.md`
- Modify: `Makefile`

- [ ] **Step 1: Implement V106 script**

Scan:
- horizons: `5, 10, 15, 30`
- probability floors: `0.0, 0.3333333333333333, 0.34, 0.35, 0.40`
- daily top-k: `1, 2, 3, 4, 5`
- fee: `8.5` bps

Passing gate:
- selector and holdout total net PnL > 0
- selector and holdout win rate > 55%
- selector and holdout active day count equals calendar day count
- selector and holdout average trades per calendar day >= 1.0
- selector and holdout calendar-positive month rate >= 50%

Selection rule must use selector fields only.

### Task 3: Verify

Run:

```bash
make test-btcusdc-v106
make btcusdc-exact-daily-coverage-classifier-v106
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

Report whether the strict every-day requirement is satisfied. If satisfied, state clearly that it remains a research candidate, not a live trading guarantee.
