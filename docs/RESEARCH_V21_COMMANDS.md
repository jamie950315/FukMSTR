# Research V21 Commands

V21 starts from the V20 BTC rule and keeps the entry rule frozen.  It changes only the slot-preserving take-profit target from 40 bps to 45 bps and audits that target against a small pre-declared exit family.

## Main command

```bash
make btc-profit-target-lock-v21
```

This writes:

```text
runs/research_v21_btc_profit_target_lock_tp45/
```

## Direct CLI command

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli btc-profit-target-lock \
  --v17-run-dir runs/research_v17_execution_profit_lock_alpha0125_tp40 \
  --out runs/research_v21_btc_profit_target_lock_tp45 \
  --taker-fee-percent 0.0400 \
  --maker-fee-percent 0.0000 \
  --horizon-sec 90 \
  --latency-sec 0.5 \
  --take-profit-bps 45 \
  --stop-loss-bps 0 \
  --exit-take-profit-candidates 0,10,15,20,25,30,35,40,45,50,55,60 \
  --stress-fee-side-bps-values 4,5,6,7.5,10 \
  --stress-latency-sec-values 0,0.5,1,2,3,5 \
  --leverage-values 1,2,3,5,10,20 \
  --shift-null-runs 1000 \
  --random-scenarios 10000 \
  --gate-min-trades 10 \
  --gate-min-hit-rate 1.0 \
  --gate-min-total-net-bps 130 \
  --gate-min-mean-net-bps 13 \
  --gate-max-family-addone-p 0.01 \
  --gate-max-stress-fee-side-bps 10 \
  --gate-max-stress-latency-sec 5 \
  --gate-extra-cost-bps 12 \
  --promoted-leverage-cap 3 \
  --clean
```

## Read result

```bash
cat reports/RESEARCH_V21_RESULTS.md
cat runs/research_v21_btc_profit_target_lock_tp45/REPORT.md
cat runs/research_v21_summary.csv
```

## Verification

```bash
python -m py_compile src/lob_microprice_lab/*.py scripts/*.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest -q tests/test_btc_profit_target_lock_v21.py
make btc-profit-target-lock-v21
```

## Frozen V21 policy

```text
V19 real-fee filters: unchanged
BTC side guard: long only, kline_15s_signal <= 0.0
short side: unchanged
entry fee model: taker + taker
real taker fee: 0.0400% per side = 4 bps per side
round-trip fee: 8 bps
horizon: 90 seconds
latency: 0.5 seconds
take profit: 45 bps
stop loss: disabled
reserved slot: enabled
promoted leverage cap: 3x research-only
```
