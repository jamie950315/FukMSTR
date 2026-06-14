# V110 Flow Sweep Regime Ensemble Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the V109 exact-daily BTCUSDC candidate by adding prior-only order-flow, sweep/divergence, and volatility-regime signals inspired by crypto microstructure research.

**Architecture:** Build a new V110 feature family on top of the V102/V106 daily top-k classifier path, then ensemble it with the existing V109 families without changing the selector/holdout split or the fee model. Selection remains selector-only and exact-daily; holdout is used only for the locked candidate audit.

**Tech Stack:** Python, pandas, scikit-learn HistGradientBoostingClassifier, pytest, Makefile.

---

### Completion Standard

- [ ] V110 must add only causal/prior-bar features.
- [ ] V110 must preserve the V106/V109 exact-daily selection discipline: probability floor `0.0`, selector-only ranking, and every calendar day active in selector and holdout.
- [ ] V110 must compare against V109 selected top5:
  - holdout PnL must improve materially, or
  - holdout drawdown must improve materially while keeping PnL close, or
  - if neither happens, V110 is documented as a failed route and not promoted.
- [ ] Unit tests must prove no lookahead in the new features and timestamp alignment in the new ensemble.
- [ ] The research command, targeted tests, full pytest suite, and build must pass before claiming completion.

### Files

- Create: `scripts/run_btcusdc_v110_flow_sweep_regime_ensemble.py`
- Create: `docs/RESEARCH_V110_COMMANDS.md`
- Create: `reports/RESEARCH_V110_BTCUSDC_FLOW_SWEEP_REGIME_ENSEMBLE_RESULTS.md`
- Modify: `tests/test_btcusdc_independent_validation_v27.py`
- Modify: `Makefile`

### Task 1: Add Causal Flow/Sweep/Regime Feature Builder

- [ ] Add `_add_flow_sweep_regime_features(bars)` to the new V110 script.
- [ ] Include prior-only features:
  - rolling signed flow mean/sum/std for windows `5, 15, 30, 60, 120, 240`
  - rolling buy-ratio mean/z-score for windows `15, 60, 240`
  - rolling trade-count and volume intensity z-scores for windows `15, 60, 240`
  - CVD slope/divergence features over windows `15, 60, 240`
  - prior high/low sweep distances and sweep flags over windows `30, 60, 240`
  - volatility regime features using prior return/range percentiles over windows `60, 240`
- [ ] Merge these features into the sampled V102 MA frame.

### Task 2: Add V110 Exact-Daily Ensemble

- [ ] Reuse V109 probability averaging and V106 exact-daily gate.
- [ ] Compare multiple ensembles:
  - `ma+flow_sweep_regime`
  - `ma+price_context+flow_sweep_regime`
  - `ma+technical+flow_sweep_regime`
  - `ma+price_context+technical+flow_sweep_regime`
- [ ] Keep horizons, daily top-k values, probability floors, split windows, and fee identical to V109.

### Task 3: Add Tests

- [ ] Add a test that mutates the current bar high/low/flow/volume and proves prior-only V110 feature values for that timestamp do not change.
- [ ] Add a test that V110 feature frame includes CVD, sweep, intensity, and regime columns.
- [ ] Add a test that V110 ensemble frame alignment preserves timestamps and averages probabilities correctly.

### Task 4: Run and Verify

- [ ] Run `make test-btcusdc-v110`.
- [ ] Run `make btcusdc-flow-sweep-regime-ensemble-v110`.
- [ ] Inspect the generated selected candidate and report.
- [ ] Run full test suite with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q`.
- [ ] Run `python -m build`.

### Task 5: Decision

- [ ] Promote V110 only if the selector-locked candidate improves significantly against V109 under the same holdout and daily-coverage rules.
- [ ] If V110 does not beat V109, keep V109 as the active best candidate and document V110's failure point.
