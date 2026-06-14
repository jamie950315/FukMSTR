# Research V162 Commands

V162 tests a small sizing boost for long trades with stronger 1440-minute `trend_follow_1440_bps` on top of the promoted V161 account path. It is a sizing adjustment only, not a new entry signal.

## Focused Test

```bash
make test-btcusdc-v162
```

## Run V162

```bash
make btcusdc-v162-long-trend-follow-boost
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

```text
runs/research_v162_long_trend_follow_boost/v162_selected_account_path.csv
runs/research_v162_long_trend_follow_boost/v162_long_trend_follow_boost_candidate.csv
runs/research_v162_long_trend_follow_boost/v162_monthly_account_return.csv
runs/research_v162_long_trend_follow_boost/v162_long_trend_follow_context_metrics.csv
runs/research_v162_long_trend_follow_boost/v162_long_trend_follow_boost_summary.json
reports/RESEARCH_V162_BTCUSDC_LONG_TREND_FOLLOW_BOOST.md
```

## Research Notes

- Base: V161 selected account path.
- Feature: `trend_follow_1440_bps`.
- Segment: `long`.
- Threshold: selector q0.80.
- Operator: `>=`.
- Modifier: additional `1.10x` on flagged trades.
- No new trades are added.
- Existing trade sides are not changed.
- Holdout is used only for validation.
- Post-trade account-path fields such as `drawdown_pct` are excluded from promotion because they are not valid entry-time signals.
- This is a research candidate, not a live trading guarantee.
