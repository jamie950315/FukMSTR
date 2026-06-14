# Research V144 Commands

V144 tests whether Binance BTCUSDC perpetual funding rates can improve the V142/V143 trend-emotion overlay as an external market sentiment signal.

Run the audit:

```bash
PYTHONPATH=src python scripts/run_btcusdc_v144_funding_sentiment_governor.py
```

Or use Make:

```bash
make btcusdc-v144-funding-sentiment-governor
```

Run focused tests:

```bash
make test-btcusdc-v144
```

Outputs:

- `runs/research_v144_funding_sentiment_governor/btc_usdc_funding_rates.csv`
- `runs/research_v144_funding_sentiment_governor/v144_v142_with_funding_sentiment_features.csv`
- `runs/research_v144_funding_sentiment_governor/v144_funding_sentiment_candidates.csv`
- `runs/research_v144_funding_sentiment_governor/v144_funding_sentiment_summary.json`
- `reports/RESEARCH_V144_BTCUSDC_FUNDING_SENTIMENT_GOVERNOR.md`

Decision rule:

- Candidate selection uses only the selector period before `2026-01-01`.
- Holdout results after `2026-01-01` are reported after selection.
- A candidate is promoted only if full-period return improves by at least 5%, full and holdout drawdown do not worsen, and every month remains positive.
