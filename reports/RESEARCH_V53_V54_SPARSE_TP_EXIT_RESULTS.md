# Research V53/V54 Results: BTCUSDC Sparse Take-Profit Exit Probe

V53/V54 continues after V51/V52 showed that medium-frequency BTCUSDC flow selectors were not stable. The new question is narrower: can true BTCUSDC public data produce a sparse, high-win-rate ledger that passes the existing V26 BTCUSDC contract gate without changing the gate?

## Data

Input bars:

```text
runs/research_v50_btcusdc_full_aggtrade_flow_input/btcusdc_full_aggtrade_1m_flow_bars.csv
```

These are the full available BTCUSDC public aggTrade-derived 1m bars:

| Item | Value |
|---|---:|
| aggTrade rows | 259,997,196 |
| 1m flow bars | 1,278,095 |
| Date range | 2024-01-04 12:31 UTC through 2026-06-10 23:59 UTC |

## V53a High-Win-Rate Search

Output:

```text
runs/research_v53a_btcusdc_high_winrate_np_probe
```

V53a searched sparse high-quantile candidates with formal non-overlapping trade accounting. The fixed-horizon exit version did not find any policy with at least 11 trades and 90% full-period win rate.

Best fixed-horizon candidates with at least 11 trades:

| Policy | Trades | Win rate | Total bps |
|---|---:|---:|---:|
| `1440|720|reversal|abs_return_bps|0.995` | 11 | 81.82% | +1967.1236 |
| `1440|1440|reversal|abs_return_bps|0.995` | 11 | 81.82% | +1797.4939 |
| `720|1440|reversal|abs_return_bps|0.995` | 12 | 75.00% | +1415.8302 |

The design-period high-win selector chose:

```text
1440|1440|reversal|abs_return_bps|0.995
```

Selection evidence:

| Period | Trades | Win rate | Total bps |
|---|---:|---:|---:|
| Design folds 1-4 | 4 | 100.00% | +1189.4686 |
| Holdout folds 5-7 | 7 | 71.43% | +608.0253 |
| Full folds 1-7 | 11 | 81.82% | +1797.4939 |

Fixed-horizon exit therefore fails the V26 win-rate gate.

## V54 Take-Profit Exit

Output:

```text
runs/research_v54_btcusdc_sparse_tp_exit_probe
runs/research_v54_btcusdc_sparse_tp_exit_contract_gate_tp80
```

V54 applies a deterministic take-profit exit to the V53a design-selected sparse rule:

```text
lookback: 1440 minutes
horizon reserve: 1440 minutes
direction: reversal
filter: abs_return_bps
quantile: 0.995
take profit: 80 bps
roundtrip taker fee: 8.0 bps
BTCUSDC quote surcharge: 0.5 bps through the existing V26 gate path
```

The 80 bps take-profit is the smallest tested TP level that passed the design-period basic gate screen:

| TP | Design trades | Design win rate | Design total | Holdout trades | Holdout win rate | Holdout total |
|---:|---:|---:|---:|---:|---:|---:|
| 80 bps | 4 | 100.00% | +286.0000 bps | 7 | 100.00% | +500.5000 bps |
| 120 bps | 4 | 100.00% | +446.0000 bps | 7 | 100.00% | +754.5905 bps |

V54 promotes the more conservative TP80 result.

## V26 Gate Result

Repro command:

```bash
make btcusdc-sparse-tp-exit-v54
```

Ledger:

```text
runs/research_v54_btcusdc_sparse_tp_exit_probe/v54_tp80_source_ledger_for_contract_gate.csv
```

Gate output:

```text
runs/research_v54_btcusdc_sparse_tp_exit_contract_gate_tp80
```

Aggregate:

| Metric | Value |
|---|---:|
| Gate passed | true |
| Trades | 11 |
| Win rate | 100.00% |
| Notional total net PnL | +786.5000 bps |
| Notional mean net PnL | +71.5000 bps/trade |
| Worst trade | +71.5000 bps |
| Account return at 8x/no compounding | +62.9200% |
| Account max drawdown | 0.0000% |
| Bootstrap positive total rate | 100.00% |
| 50% missed-trade p05 account return | +17.1600% |
| Extra +16 bps/trade account return | +48.8400% |
| Four synthetic -40 bps failures min account return | +40.1225% |
| Four synthetic -40 bps failures worst drawdown | -3.2000% |

All V26 gate checks passed.

## Caveat

V54 is not the frozen V26 transfer rule. It is a new sparse BTCUSDC rule discovered after the true V26 replay failed. It passes the existing V26 gate on the full available public BTCUSDC range, and TP80 was selected using the design-period screen, but the final promoted ledger still has only 11 trades. This is a valid gate-pass research artifact, not a claim of broad production robustness without future unseen data.

