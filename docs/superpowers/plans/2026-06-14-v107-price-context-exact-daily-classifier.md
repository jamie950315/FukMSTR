# V107 Price Context Exact Daily Classifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the V106 exact-daily BTCUSDC classifier by adding prior high/low, range-position, volatility, and volume-statistic features without relaxing the strict daily trading gate.

**Architecture:** Reuse V106 exact-daily scan and V104 HGB classifier execution. Add a V107 feature frame that extends V102 MA features with price-context features computed only from prior bars, then compare selector-locked exact-daily results against V106.

**Tech Stack:** Python, pandas, scikit-learn, pytest, Makefile.

---

### Task 1: Price Context Feature Contract

**Files:**
- Modify: `tests/test_btcusdc_independent_validation_v27.py`
- Create: `scripts/run_btcusdc_v107_price_context_exact_daily_classifier.py`

- [ ] **Step 1: Write failing tests**

Add tests that import V107 and verify:
- `_add_price_context_features()` computes rolling high/low features from prior bars only.
- `_price_context_feature_frame()` includes the new feature columns alongside existing MA features.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v107_price_context_features_use_prior_high_low_without_lookahead tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v107_feature_frame_includes_price_context_columns
```

Expected: FAIL because the V107 script does not exist yet.

### Task 2: V107 Script and Commands

**Files:**
- Create: `scripts/run_btcusdc_v107_price_context_exact_daily_classifier.py`
- Create: `docs/RESEARCH_V107_COMMANDS.md`
- Modify: `Makefile`

- [ ] **Step 1: Implement V107 script**

Feature additions:
- prior high/low distance in bps for windows `15, 30, 60, 120, 240`
- rolling range position for the same windows
- rolling range width in bps for the same windows
- realized volatility for the same windows
- prior volume z-score for windows `30, 60, 120, 240`

Scan:
- horizons: `5, 10, 15, 30`
- probability floors: `0.0, 1/3, 0.34, 0.35, 0.40`
- daily top-k: `1, 2, 3, 4, 5`
- fee: `8.5` bps

Gate:
- selector and holdout total net PnL > 0
- selector and holdout win rate > 55%
- selector and holdout active day count equals calendar day count
- selector and holdout average trades per calendar day >= 1.0
- selector and holdout calendar-positive month rate >= 50%

Selection rule:
- only candidates with `probability_floor == 0.0` can be selector-locked
- rank by selector PnL, selector win rate, selector positive-month rate, selector trades/day

### Task 3: Verify and Compare

Run:

```bash
make test-btcusdc-v107
make btcusdc-price-context-exact-daily-classifier-v107
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

Compare V107 selected candidate against V106 selected candidate on:
- selector total PnL
- selector win rate
- holdout total PnL
- holdout win rate
- holdout max drawdown
- exact daily coverage

Report whether V107 improves V106 or not. Do not claim live trading readiness.
