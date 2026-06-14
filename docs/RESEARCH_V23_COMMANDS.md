# V23 BTC Adaptive Safety Lock Commands

V23 starts from the frozen V22 BTC rescue-profit rule. It does not change the signal, entry, exit, horizon, or fee assumptions. It adds an account-level adaptive leverage safety certificate.

## Main run

```bash
make btc-adaptive-safety-lock-v23
```

Direct command:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
PYTHONPATH=src python scripts/run_btc_adaptive_safety_lock_v23.py
```

## Tests

```bash
make test-btc-v23
```

## Important output files

```text
runs/research_v23_btc_adaptive_safety_lock/REPORT_V23.md
runs/research_v23_btc_adaptive_safety_lock/summary_v23.json
runs/research_v23_btc_adaptive_safety_lock/btc_adaptive_account_path.csv
runs/research_v23_btc_adaptive_safety_lock/btc_adaptive_leverage_policy_scan.csv
runs/research_v23_btc_adaptive_safety_lock/btc_synthetic_loss_injection_stress.csv
runs/research_v23_btc_adaptive_safety_lock/btc_v23_account_level_stress_summary.csv
```

## Frozen V23 live-research policy

```text
trade rule: V22 unchanged
horizon: 90 sec
fee: taker 0.0400% per side, maker 0.0000%
round-trip route used for research: taker + taker = 8 bps
entry/exit: V22, take profit 52 bps, no stop loss, reserved horizon slot
normal leverage research cap: 5x
risk-off leverage: 4x
risk-off trigger: any realized trade <= -20 bps notional
risk-off duration: next 3 trades
```

## Gate additions in V23

```text
V22 base gate must pass under 5x promoted shock buffer
all 10 bps/side + 5 sec stress must remain positive
50% missed-trade p05 account return must remain positive
extra +16 bps per trade reserve must remain positive
synthetic 3-loss account stress must remain positive
synthetic 3-loss worst drawdown must stay above -5%
```

## Caveat

V23 is still a bundled-sample research certificate. It must be forward-validated on independent BTCUSDT contract data without changing the V22 signal or the V23 leverage policy.
