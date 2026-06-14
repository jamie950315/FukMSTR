# Research V24 commands: BTC adaptive exit + safety lock

V24 continues from V22/V23 without changing the BTC entry rule. It adds a slot-preserving adaptive take-profit ladder and then applies the account-level safety governor.

## Main commands

Run the trade-level adaptive exit certificate:

```bash
make btc-adaptive-exit-lock-v24
```

Run the promoted account-level safety certificate:

```bash
make btc-adaptive-exit-safety-lock-v24
```

Run V24 tests:

```bash
make test-btc-v24
```

## Read outputs

```bash
cat reports/RESEARCH_V24_RESULTS.md
cat runs/research_v24_btc_adaptive_exit_lock/REPORT.md
cat runs/research_v24_btc_adaptive_exit_safety_lock/REPORT.md
```

Key CSVs:

```text
runs/research_v24_btc_adaptive_exit_lock/btc_adaptive_exit_trade_ledger.csv
runs/research_v24_btc_adaptive_exit_lock/btc_v22_v24_exit_comparison.csv
runs/research_v24_btc_adaptive_exit_lock/btc_adaptive_fee_latency_stress.csv
runs/research_v24_btc_adaptive_exit_safety_lock/btc_v24_adaptive_account_path.csv
runs/research_v24_btc_adaptive_exit_safety_lock/btc_v24_synthetic_loss_injection_stress.csv
runs/research_v24_btc_adaptive_exit_safety_lock/btc_v24_account_level_stress_summary.csv
```

## Direct Python entry points

```bash
PYTHONPATH=src python scripts/run_btc_adaptive_exit_lock_v24.py
PYTHONPATH=src python scripts/run_btc_adaptive_exit_safety_lock_v24.py
```

## Direct CLI

```bash
PYTHONPATH=src python -m lob_microprice_lab.cli btc-adaptive-exit-lock \
  --v17-run-dir runs/research_v17_execution_profit_lock_alpha0125_tp40 \
  --out runs/research_v24_btc_adaptive_exit_lock \
  --taker-fee-percent 0.0400 \
  --maker-fee-percent 0.0000 \
  --shift-null-runs 1000 \
  --clean
```

## Frozen V24 trade rule

```text
BTC entries: V19 high-fee filters + V20 side guard + V22 rescue lane
Trade route: taker entry + taker exit
Fee: 0.0400% taker per side, 0.0000% maker per side
Round trip fee used in promoted route: 8 bps
Horizon: 90 sec
Latency: 0.5 sec
Stop loss: disabled
Reserve horizon slot: true
```

Adaptive take-profit ladder:

```text
Long default take profit: 52 bps
Short default take profit: 45 bps
Short compression: if kline_15s_signal >= 0.45, take profit = 25 bps
Soft long compression: if prob_edge <= 0.20 and kline_15s_signal <= -0.40, take profit = 20 bps
```

Account safety layer:

```text
Normal leverage cap: 5x research-only
Risk-off leverage: 4x
Risk-off trigger: realized trade <= -20 bps notional
Risk-off duration: next 3 trades
```

## Warning

This is still a bundled-sample research certificate. Do not retune the entry thresholds, rescue lane, or adaptive take-profit ladder on the same bundled sample. The next valid upgrade is independent multi-day BTCUSDT contract validation.
