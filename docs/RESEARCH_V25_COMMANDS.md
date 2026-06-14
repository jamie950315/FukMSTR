# Research V25 Commands

Run the V25 BTC portfolio risk lock:

```bash
make btc-portfolio-risk-lock-v25
```

Direct command:

```bash
PYTHONPATH=src python scripts/run_btc_portfolio_risk_lock_v25.py
```

Read the generated report:

```bash
cat reports/RESEARCH_V25_RESULTS.md
cat runs/research_v25_btc_portfolio_risk_lock/REPORT_V25.md
cat runs/research_v25_btc_portfolio_risk_lock/summary_v25.json
```

Run targeted V25 tests:

```bash
make test-btc-v25-portfolio
```

Run the broad existing split:

```bash
make test-split
```

## V25 frozen policy

```text
source trading rule: V24 BTC adaptive exit safety lock
prediction window: 90 seconds
user fee: taker 0.0400% per side, maker 0.0000%
research route: taker + taker = 8 bps round trip
normal leverage: 8.0x
emergency leverage: 6.75x
emergency trigger: realized trade <= -20 bps notional
emergency duration: next 10 trades
promoted synthetic loss stress: four -40 bps notional failures
```
