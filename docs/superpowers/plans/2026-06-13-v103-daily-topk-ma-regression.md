# V103 Daily Top-K MA Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test whether MA-feature regression can reach the high-frequency target by selecting the strongest non-overlapping predictions per calendar day.

**Architecture:** Reuse V102 MA feature construction and V101 regression training. Replace fixed edge-only execution with a daily top-k selector that ranks by absolute predicted return, applies an optional minimum edge floor, and evaluates selector plus holdout under the same 8.5 bps cost and strict high-frequency gate.

**Tech Stack:** Python, pandas, scikit-learn, pytest, Makefile.

---

### Task 1: Daily Top-K Ledger Contract

**Files:**
- Modify: `tests/test_btcusdc_independent_validation_v27.py`
- Create: `scripts/run_btcusdc_v103_daily_topk_ma_regression.py`

- [ ] **Step 1: Write the failing tests**

Add tests that import V103 and verify:
- `_daily_topk_prediction_ledger()` chooses the largest absolute predicted returns per UTC day.
- It respects horizon spacing inside each day.
- It assigns long/short direction from the sign of `predicted_return_bps`.
- `_passes_daily_topk_gate()` keeps the existing profit, win-rate, frequency, and month-stability gate.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v103_daily_topk_ledger_selects_ranked_non_overlapping_predictions tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v103_gate_requires_profit_win_frequency_and_months
```

Expected: FAIL because `scripts/run_btcusdc_v103_daily_topk_ma_regression.py` does not exist yet.

### Task 2: V103 Script and Report

**Files:**
- Create: `scripts/run_btcusdc_v103_daily_topk_ma_regression.py`
- Create: `docs/RESEARCH_V103_COMMANDS.md`
- Modify: `Makefile`

- [ ] **Step 1: Implement V103 script**

Use V102 `_ma_feature_frame()`, V101 `_fit_regressor()`, and V101 `_prediction_frame()`.

Scan:
- horizons: `15, 30, 60`
- min edge floors: `0.0, 4.0, 8.5, 10.0, 12.5`
- daily top-k: `1, 2, 3`
- fee: `8.5` bps

Evaluate selector and holdout separately. Passing requires:
- selector and holdout total net PnL > 0
- selector and holdout win rate > 55%
- selector and holdout average trades per calendar day >= 1.0
- selector and holdout calendar-positive month rate >= 50%

- [ ] **Step 2: Add Make targets**

```make
btcusdc-daily-topk-ma-regression-v103:
	PYTHONPATH=src python scripts/run_btcusdc_v103_daily_topk_ma_regression.py

test-btcusdc-v103:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v103_daily_topk_ledger_selects_ranked_non_overlapping_predictions tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v103_gate_requires_profit_win_frequency_and_months
```

- [ ] **Step 3: Run V103**

Run:

```bash
make test-btcusdc-v103
make btcusdc-daily-topk-ma-regression-v103
```

Expected outputs:
- `runs/research_v103_btcusdc_daily_topk_ma_regression/v103_daily_topk_candidates.csv`
- `runs/research_v103_btcusdc_daily_topk_ma_regression/v103_daily_topk_passed_candidates.csv`
- `runs/research_v103_btcusdc_daily_topk_ma_regression/v103_summary.json`
- `reports/RESEARCH_V103_BTCUSDC_DAILY_TOPK_MA_REGRESSION_RESULTS.md`

### Task 3: Verification

**Files:**
- Inspect: `reports/RESEARCH_V103_BTCUSDC_DAILY_TOPK_MA_REGRESSION_RESULTS.md`
- Inspect: `runs/research_v103_btcusdc_daily_topk_ma_regression/v103_summary.json`

- [ ] **Step 1: Run targeted tests**

```bash
make test-btcusdc-v103
```

- [ ] **Step 2: Run full tests**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
```

- [ ] **Step 3: Run build**

```bash
python -m build
```

- [ ] **Step 4: Report result**

If no candidate passes, keep the active goal incomplete and explain which gate failed. If a candidate passes, treat it as a research candidate only and still state that it is not a live trading guarantee.
