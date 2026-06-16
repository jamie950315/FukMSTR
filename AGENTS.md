# Agent Instructions

## Project State

This repository is the public `FukMSTR` research workspace for BTCUSDC short-term trading research, replay, and paper-trading tools.

Current active safety state is V219:

- V142 remains the paper-trading and historical replay baseline.
- Old account-path ledgers still backfill `Side` from the V119 signal reference when `signal` is omitted.
- V204 is the real-money readiness gate and must block launch unless all evidence gates pass.
- V206 is the final real-money launch preflight and must block launch unless V204 is ready, the operator explicitly arms real-money mode, and runtime source files are clean.
- V212, V214, V216, V218, and V219 add forward freshness, public data availability, execution/signal provenance, source provenance, and input hash locks.
- As of V219, the real-money path is still blocked until fresh forward evidence and execution validation are clean.

This is a research candidate, not a live trading system. Do not describe historical backtests as proof of future profit.

## Communication

- User-facing replies should be in Traditional Chinese unless the user explicitly asks otherwise.
- README files must be written in English unless the user explicitly requests another language.
- Keep explanations direct and understandable for a smart user who is not reading the code.

## Repository Hygiene

- Do not commit large generated artifacts or local market data.
- Keep these paths ignored:
  - `data/`
  - `runs/`
  - `build/`
  - `dist/`
  - `.pytest_cache/`
  - `*.egg-info/`
- Do not commit credentials, API keys, exchange secrets, private keys, or `.env` files.
- Before publishing, scan for obvious secrets and oversized files.

## Development Rules

- Prefer existing project patterns over new abstractions.
- Use `rg` / `rg --files` for searching.
- Keep changes scoped to the user request.
- Use structured parsers/APIs for structured data instead of ad hoc string parsing when practical.
- Use `apply_patch` for manual source edits.
- Do not use destructive git commands unless the user explicitly asks.

## Verification

Before saying work is complete, run the relevant checks. For repo-wide changes, run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

For V142-focused changes, also use the relevant target:

```bash
make test-btcusdc-v142
make test-paper-trading-v142
make test-trade-replay-v142
```

For current real-money readiness/preflight safety changes, also use:

```bash
make test-btcusdc-v219
make btcusdc-v204-real-money-readiness-gate
make btcusdc-v206-real-money-launch-preflight
PYTHONPATH=src python -m lob_microprice_lab.cli real-trade-btcusdc --out runs/research_v207_real_trade_cli_preflight --arm-real-money-token I_UNDERSTAND_THIS_USES_REAL_MONEY
```

If a check fails, fix the issue before reporting completion.

## Data And Trading Claims

- Treat reports as research evidence only.
- Mention that forward monitoring and execution validation are still required before live use.
- Do not tune thresholds merely to improve historical results unless the user explicitly asks for research exploration.
- Do not claim the paper-trading tool places real orders. It is local simulation only.

## Web Usage

When web research is needed, prefer primary sources and official documentation. In this local Codex setup, use the `ccsearch` skill for web search/fetch if it is available.
