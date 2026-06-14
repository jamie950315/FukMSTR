# Research V26 Full Available BTCUSDC Public Replay Results

This run completes the requested true BTCUSDC replay path as far as Binance public files are available from the generated V26 download plan. No strategy thresholds were changed.

## Data download

Source plan:

```text
runs/research_v26_btcusdc_contract_lock/btcusdc_data_plan/download_commands.sh
```

Download audit:

| Item | Count |
|---|---:|
| Manifest data rows | 7136 |
| Downloaded data files | 4445 |
| Missing data files | 2691 |
| Available BTCUSDC 1m kline days | 889 |
| Available 1m date range | 2024-01-04 through 2026-06-10 |

Missing files are remote 404s, not local threshold or strategy changes. Binance did not provide the planned BTCUSDC `1s`, `5s`, and `15s` kline files for this range, and the first three dates in the plan were unavailable for the other requested data types.

Audit files:

```text
runs/research_v26_btcusdc_full_public_replay_input/download_manifest_status.csv
runs/research_v26_btcusdc_full_public_replay_input/missing_manifest_rows.csv
runs/research_v26_btcusdc_full_download/download_failures.csv
```

## True ledger replay

Ledger:

```text
runs/research_v26_btcusdc_full_public_replay_input/btcusdc_public_1m_full_available_replay_ledger.csv
```

Run output:

```text
runs/research_v26_btcusdc_full_public_replay
```

The replay uses `run_btcusdc_contract_lock(..., btcusdc_ledger=...)` with the frozen V26 policy and the full available BTCUSDC public 1m kline replay ledger.

## Main result

| Metric | Full available BTCUSDC public replay |
|---|---:|
| Gate passed | false |
| Data mode | true_btcusdc_ledger |
| True BTCUSDC data run completed | true |
| Trades | 9768 |
| Selected-trade win rate | 13.74% |
| Notional total net PnL | -84236.9648 bps |
| Notional mean net PnL | -8.6238 bps/trade |
| Notional median net PnL | -8.5000 bps/trade |
| Worst trade | -107.8642 bps |
| Account return at 8x/no compounding with emergency governor | -6007.1317% |
| Account max drawdown | -6007.1317% |
| Bootstrap positive total rate | 0.00% |
| 50% missed-trade p05 account return | -3456.8369% |
| Extra +16 bps/trade account return | -19241.9972% |
| Four synthetic -40 bps failures min account return | -6018.8133% |

Failed gate checks:

```text
win_rate
total_net_pnl
mean_net_pnl
no_loss_account_return
missed_trade_account_return
extra_cost_account_return
synthetic_loss_return
synthetic_loss_drawdown
```

## Conclusion

The transfer-proxy V26 pass does not survive the true BTCUSDC public replay. With real BTCUSDC 1m public data over the available 2024-01-04 through 2026-06-10 range, the frozen strategy loses heavily and fails the promoted BTCUSDC gate.
