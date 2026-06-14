# V102 MA Feature Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add MA7, MA25, and MA99 trend-structure features to the BTCUSDC high-frequency search and evaluate whether they improve the V101 thick-edge route.

**Architecture:** Reuse the V101 return-magnitude regression scan, but extend the feature frame with non-leaking MA features computed from prior close prices. Evaluate selector and holdout under the same 8.5 bps cost and high-frequency gate.

**Tech Stack:** Python, pandas, sklearn HistGradientBoostingRegressor, pytest, Makefile.

---

### Task 1: V102 Tests

**Files:**
- Modify: `tests/test_btcusdc_independent_validation_v27.py`

- [ ] **Step 1: Write failing tests**

Add tests that import `scripts/run_btcusdc_v102_ma_feature_regression.py` and verify:
- `_add_ma_features()` computes MA7, MA25, and MA99 from prior close values, not current close.
- `_ma_feature_frame()` includes MA distance, MA spread, MA slope, and stack features in the model feature columns.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v102_ma_features_use_prior_close_without_lookahead tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v102_feature_frame_includes_ma_columns
```

Expected: FAIL because the V102 script does not exist yet.

### Task 2: V102 Runner

**Files:**
- Create: `scripts/run_btcusdc_v102_ma_feature_regression.py`
- Modify: `Makefile`
- Create: `docs/RESEARCH_V102_COMMANDS.md`

- [ ] **Step 1: Implement MA feature frame**

Add features:
- `ma7_dist_bps`, `ma25_dist_bps`, `ma99_dist_bps`
- `ma7_ma25_spread_bps`, `ma25_ma99_spread_bps`
- `ma7_slope_5_bps`, `ma25_slope_5_bps`, `ma99_slope_5_bps`
- `ma_stack_long`, `ma_stack_short`

- [ ] **Step 2: Reuse V101 scan behavior**

Use the same horizons, thresholds, fee, selector/holdout split, ledger construction, and gate as V101. Only the feature set changes.

- [ ] **Step 3: Add outputs**

Write:
- `runs/research_v102_btcusdc_ma_feature_regression/v102_ma_feature_candidates.csv`
- `runs/research_v102_btcusdc_ma_feature_regression/v102_ma_feature_passed_candidates.csv`
- `runs/research_v102_btcusdc_ma_feature_regression/v102_summary.json`
- `reports/RESEARCH_V102_BTCUSDC_MA_FEATURE_REGRESSION_RESULTS.md`

### Task 3: Run And Verify

**Files:**
- Generated: `runs/research_v102_btcusdc_ma_feature_regression/*`
- Generated: `reports/RESEARCH_V102_BTCUSDC_MA_FEATURE_REGRESSION_RESULTS.md`

- [ ] **Step 1: Run focused tests**

Run:

```bash
make test-btcusdc-v102
```

- [ ] **Step 2: Run V102**

Run:

```bash
make btcusdc-ma-feature-regression-v102
```

- [ ] **Step 3: Run full verification**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

- [ ] **Step 4: Interpret**

If no candidate passes, state clearly whether MA features improved any partial gate counts or whether the route remains unpromoted.
