# Research V163 Commands

V163 audits the post-V162 search space after excluding unsuitable account-path fields and already-promoted same-family features. It is a no-promotion audit unless a clean independent candidate clears the gate.

## Focused Test

```bash
make test-btcusdc-v163
```

## Run V163 Audit

```bash
make btcusdc-v163-post-v162-candidate-audit
```

## Full Verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q
python -m build
```

## Outputs

```text
runs/research_v163_post_v162_candidate_audit/v163_passed_candidates.csv
runs/research_v163_post_v162_candidate_audit/v163_candidate_rejection_summary.csv
runs/research_v163_post_v162_candidate_audit/v163_post_v162_candidate_audit_summary.json
reports/RESEARCH_V163_BTCUSDC_POST_V162_CANDIDATE_AUDIT.md
```

## Research Notes

- Base: V162 selected account path.
- Excludes post-trade/account-path result fields, including `drawdown_pct`.
- Excludes already-promoted same-family fields: `day_sofar_count`, `trend_follow_1440_bps`, and duplicate `prior_ret_1440_bps`.
- Holdout is used only for validation.
- A no-promotion result is valid when no clean independent candidate clears return, drawdown, worst-month, and positive-month gates.
- This is a research audit, not a live trading guarantee.
