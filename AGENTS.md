# Agent Instructions

## Project State

This repository is the public `FukMSTR` research workspace for BTCUSDC short-term trading research, replay, and paper-trading tools.

Current promoted handoff state is V142:

- BTCUSDC historical trade replay page
- Side backfill from V119 signal reference when old account-path ledgers omit `signal`
- V142 paper-trading MVP
- High-confidence rescue 5x leverage path with drawdown throttling

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

If a check fails, fix the issue before reporting completion.

## Data And Trading Claims

- Treat reports as research evidence only.
- Mention that forward monitoring and execution validation are still required before live use.
- Do not tune thresholds merely to improve historical results unless the user explicitly asks for research exploration.
- Do not claim the paper-trading tool places real orders. It is local simulation only.

## Web Usage

When web research is needed, prefer primary sources and official documentation. In this local Codex setup, use the `ccsearch` skill for web search/fetch if it is available.
