# V108 Technical Indicator Exact Daily Classifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test whether adding classic technical indicators improves the V106 exact-daily BTCUSDC classifier without relaxing the strict daily trading gate.

**Architecture:** Reuse the V106 exact-daily classifier scan and V104 HGB execution path. Extend the V102 MA feature frame with prior-bar RSI, MACD, Bollinger, ATR, and stochastic-style features, then compare the selector-locked result against V106.

**Tech Stack:** Python, pandas, scikit-learn, pytest, Makefile.

---

### Task 1: Technical Indicator Feature Contract

**Files:**
- Modify: `tests/test_btcusdc_independent_validation_v27.py`
- Create: `scripts/run_btcusdc_v108_technical_indicator_exact_daily_classifier.py`

- [ ] **Step 1: Write failing tests**

Add tests that import V108 and verify:
- `_add_technical_indicator_features()` computes RSI, Bollinger, ATR, and MACD features from prior bars only.
- `_technical_indicator_feature_frame()` includes the new feature columns with existing MA features.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v108_technical_indicators_use_prior_bars_without_lookahead tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v108_feature_frame_includes_technical_indicator_columns
```

Expected: FAIL because the V108 script does not exist yet.

### Task 2: V108 Script and Commands

**Files:**
- Create: `scripts/run_btcusdc_v108_technical_indicator_exact_daily_classifier.py`
- Create: `docs/RESEARCH_V108_COMMANDS.md`
- Modify: `Makefile`

- [ ] **Step 1: Implement V108 script**

Feature additions:
- RSI windows `7, 14, 28`
- MACD line, signal, histogram, and line-vs-price bps from prior close
- Bollinger z-score, width, upper distance, lower distance for windows `20, 60`
- ATR bps for windows `14, 30`
- stochastic position using prior high/low for windows `14, 30`

Scan:
- horizons: `5, 10, 15, 30`
- probability floors: `0.0, 1/3, 0.34, 0.35, 0.40`
- daily top-k: `1, 2, 3, 4, 5`
- fee: `8.5` bps

Gate and selection remain identical to V106.

### Task 3: Verify and Compare

Run:

```bash
make test-btcusdc-v108
make btcusdc-technical-indicator-exact-daily-classifier-v108
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

Compare V108 selected candidate against V106 selected candidate on:
- selector total PnL
- selector win rate
- holdout total PnL
- holdout win rate
- holdout max drawdown
- exact daily coverage

Report whether V108 improves V106 or not. Do not claim live trading readiness.
