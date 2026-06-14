# Research V30 Commands

V30 audits the gap between the broad candidate-set oracle and the calibration-return selector.

## Run

```bash
make btcusdc-oracle-gap-v30
```

Input:

```text
runs/research_v29_btcusdc_ytd_rolling_broad_probe/btcusdc_v28_candidate_evaluations.csv
```

## Test

```bash
make test-btcusdc-v30
```

## Outputs

```text
runs/research_v30_btcusdc_oracle_gap/summary_v30.json
runs/research_v30_btcusdc_oracle_gap/REPORT_V30.md
runs/research_v30_btcusdc_oracle_gap/btcusdc_v30_oracle_gap_folds.csv
```

## Caveat

Oracle performance uses validation outcomes and is not tradable. V30 is a diagnosis of selection failure.
