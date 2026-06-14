# V109 Feature Family Ensemble Exact Daily Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test whether averaging the MA-only, price-context, and technical-indicator model probabilities improves the V106 exact-daily BTCUSDC strategy.

**Architecture:** Train three HGB classifiers per horizon using V102, V107, and V108 feature frames. Average their down/flat/up probabilities by timestamp, then reuse the V106 exact-daily scan and selector-only lock.

**Tech Stack:** Python, pandas, scikit-learn, pytest, Makefile.

---

### Task 1: Ensemble Probability Contract

**Files:**
- Modify: `tests/test_btcusdc_independent_validation_v27.py`
- Create: `scripts/run_btcusdc_v109_feature_family_ensemble_exact_daily.py`

- [ ] **Step 1: Write failing tests**

Add tests that import V109 and verify:
- `_average_probability_frames()` averages `prob_down`, `prob_flat`, and `prob_up` by timestamp.
- It keeps `future_return_bps` aligned and sorted.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v109_average_probability_frames_aligns_by_timestamp
```

Expected: FAIL because the V109 script does not exist yet.

### Task 2: V109 Script and Commands

**Files:**
- Create: `scripts/run_btcusdc_v109_feature_family_ensemble_exact_daily.py`
- Create: `docs/RESEARCH_V109_COMMANDS.md`
- Modify: `Makefile`

- [ ] **Step 1: Implement V109 script**

Feature families:
- `ma`: V102 MA feature frame
- `price_context`: V107 price-context feature frame
- `technical`: V108 technical-indicator feature frame

Scan:
- horizons: `5, 10, 15, 30`
- probability floors: `0.0, 1/3, 0.34, 0.35, 0.40`
- daily top-k: `1, 2, 3, 4, 5`
- fee: `8.5` bps

Gate and selector-lock remain identical to V106.

### Task 3: Verify and Compare

Run:

```bash
make test-btcusdc-v109
make btcusdc-feature-family-ensemble-exact-daily-v109
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

Compare V109 selected candidate against V106 selected candidate on selector/holdout PnL, win rate, max drawdown, and exact daily coverage.
