# V105 Selector-Locked V104 Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lock the V104 strategy using selector-only evidence and then audit whether the locked strategy passes the untouched holdout window.

**Architecture:** Consume the V104 candidate table, filter only candidates that pass selector profit, win-rate, frequency, and month-stability requirements, select the best one using selector metrics only, and report holdout results without using holdout to rank or choose the policy.

**Tech Stack:** Python, pandas, pytest, Makefile.

---

### Task 1: Selector-Locked Decision Contract

**Files:**
- Modify: `tests/test_btcusdc_independent_validation_v27.py`
- Create: `scripts/run_btcusdc_v105_selector_locked_v104_audit.py`

- [ ] **Step 1: Write the failing tests**

Add tests that import V105 and verify:
- `_passes_selector_gate()` ignores holdout fields and only checks selector profit, win rate, daily frequency, and calendar-positive month rate.
- `_selector_locked_decision()` selects the best selector candidate even when another row has better holdout performance.
- The final goal is satisfied only when the selector-locked row also passes holdout gates.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v105_selector_locked_decision_ignores_holdout_ranking tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v105_selector_gate_uses_selector_fields_only
```

Expected: FAIL because `scripts/run_btcusdc_v105_selector_locked_v104_audit.py` does not exist yet.

### Task 2: V105 Audit Script and Commands

**Files:**
- Create: `scripts/run_btcusdc_v105_selector_locked_v104_audit.py`
- Create: `docs/RESEARCH_V105_COMMANDS.md`
- Modify: `Makefile`

- [ ] **Step 1: Implement V105 script**

Load `runs/research_v104_btcusdc_ma_hgb_daily_topk_classifier/v104_ma_hgb_daily_topk_candidates.csv`. If missing, run V104 first.

Selector ranking:
1. selector_total_net_pnl_bps descending
2. selector_win_rate descending
3. selector_calendar_positive_month_rate descending
4. selector_avg_trades_per_calendar_day descending

Report:
- selected policy
- selector metrics
- holdout metrics
- whether holdout passed the unchanged gate
- whether the goal is satisfied by selector-locked selection

- [ ] **Step 2: Add Make targets**

```make
btcusdc-selector-locked-v104-audit-v105:
	PYTHONPATH=src python scripts/run_btcusdc_v105_selector_locked_v104_audit.py

test-btcusdc-v105:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v105_selector_locked_decision_ignores_holdout_ranking tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v105_selector_gate_uses_selector_fields_only
```

### Task 3: Verify

**Files:**
- Inspect: `reports/RESEARCH_V105_BTCUSDC_SELECTOR_LOCKED_V104_AUDIT_RESULTS.md`
- Inspect: `runs/research_v105_btcusdc_selector_locked_v104_audit/v105_summary.json`

- [ ] **Step 1: Run V105 tests**

```bash
make test-btcusdc-v105
```

- [ ] **Step 2: Run V105 audit**

```bash
make btcusdc-selector-locked-v104-audit-v105
```

- [ ] **Step 3: Run full tests and build**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

- [ ] **Step 4: Report result**

If the selector-locked strategy passes holdout, state it is the strongest research candidate so far, not a live trading guarantee. If it fails holdout, keep the goal incomplete and state which holdout gate failed.
