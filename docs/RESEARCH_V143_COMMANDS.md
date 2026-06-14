# Research V143 Commands

V143 audits whether prior-only BTCUSDC market emotion and trend context can improve the fixed V142 candidate.

Run the audit:

```bash
PYTHONPATH=src python scripts/run_btcusdc_v143_market_emotion_trend_audit.py
```

Or use Make:

```bash
make btcusdc-v143-market-emotion-trend-audit
```

Run the focused tests:

```bash
make test-btcusdc-v143
```

Outputs:

- `runs/research_v143_market_emotion_trend_audit/v143_v142_with_market_emotion_trend_features.csv`
- `runs/research_v143_market_emotion_trend_audit/v143_market_emotion_trend_candidates.csv`
- `runs/research_v143_market_emotion_trend_audit/v143_market_emotion_trend_bucket_summary.csv`
- `runs/research_v143_market_emotion_trend_audit/v143_market_emotion_trend_summary.json`
- `reports/RESEARCH_V143_BTCUSDC_MARKET_EMOTION_TREND_AUDIT.md`

Decision rule:

- Candidate selection uses only the selector period before `2026-01-01`.
- Holdout results after `2026-01-01` are reported after selection.
- A candidate is not promoted unless it improves holdout and full-period return without worsening drawdown and keeps every month positive.
