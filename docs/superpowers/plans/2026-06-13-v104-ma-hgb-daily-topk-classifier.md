# V104 MA HGB Daily Top-K Classifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test whether a MA-feature HGB classifier can satisfy the high-frequency BTCUSDC goal by selecting the most confident non-overlapping direction predictions per day.

**Architecture:** Reuse V102 MA feature construction and V96 fee-aware labels. Train a HistGradientBoostingClassifier to predict down/flat/up classes, then rank each day by directional probability and evaluate selector plus holdout under the unchanged 8.5 bps cost gate.

**Tech Stack:** Python, pandas, scikit-learn, pytest, Makefile.

---

### Task 1: Probability Daily Top-K Ledger Contract

**Files:**
- Modify: `tests/test_btcusdc_independent_validation_v27.py`
- Create: `scripts/run_btcusdc_v104_ma_hgb_daily_topk_classifier.py`

- [ ] **Step 1: Write the failing tests**

Add tests that import V104 and verify:
- `_daily_topk_probability_ledger()` ranks rows by the stronger of `prob_up` and `prob_down`.
- It selects the signal from the larger direction probability.
- It respects horizon spacing inside each UTC day.
- It applies the probability floor.
- `_passes_daily_classifier_gate()` keeps the strict profit, win-rate, frequency, and month-stability gate.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v104_daily_topk_probability_ledger_selects_confident_non_overlapping_predictions tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v104_gate_requires_profit_win_frequency_and_months
```

Expected: FAIL because `scripts/run_btcusdc_v104_ma_hgb_daily_topk_classifier.py` does not exist yet.

### Task 2: V104 Script and Commands

**Files:**
- Create: `scripts/run_btcusdc_v104_ma_hgb_daily_topk_classifier.py`
- Create: `docs/RESEARCH_V104_COMMANDS.md`
- Modify: `Makefile`

- [ ] **Step 1: Implement V104 script**

Scan:
- horizons: `5, 10, 15, 30`
- probability floors: `0.34, 0.40, 0.45, 0.50, 0.55, 0.60`
- daily top-k: `1, 2, 3`
- fee: `8.5` bps

Passing gate remains:
- selector and holdout total net PnL > 0
- selector and holdout win rate > 55%
- selector and holdout average trades per calendar day >= 1.0
- selector and holdout calendar-positive month rate >= 50%

- [ ] **Step 2: Add Make targets**

```make
btcusdc-ma-hgb-daily-topk-classifier-v104:
	PYTHONPATH=src python scripts/run_btcusdc_v104_ma_hgb_daily_topk_classifier.py

test-btcusdc-v104:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v104_daily_topk_probability_ledger_selects_confident_non_overlapping_predictions tests/test_btcusdc_independent_validation_v27.py::test_btcusdc_v104_gate_requires_profit_win_frequency_and_months
```

### Task 3: Run and Verify

**Files:**
- Inspect: `reports/RESEARCH_V104_BTCUSDC_MA_HGB_DAILY_TOPK_CLASSIFIER_RESULTS.md`
- Inspect: `runs/research_v104_btcusdc_ma_hgb_daily_topk_classifier/v104_summary.json`

- [ ] **Step 1: Run targeted tests**

```bash
make test-btcusdc-v104
```

- [ ] **Step 2: Run V104 scan**

```bash
make btcusdc-ma-hgb-daily-topk-classifier-v104
```

- [ ] **Step 3: Run full tests**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
```

- [ ] **Step 4: Run build**

```bash
python -m build
```

- [ ] **Step 5: Report result**

If no candidate passes, state which gate fails. If a candidate passes, state it remains a research candidate, not a live trading guarantee.
