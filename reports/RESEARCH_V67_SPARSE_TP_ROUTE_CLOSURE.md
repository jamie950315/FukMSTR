# Research V67 Sparse TP Route Closure

## Decision

- Promote sparse TP route: `False`
- Status: `reject`
- Primary reasons: `true_btcusdc_replay_failed;v60_dense_holdout_not_fully_robust;design_robust_selector_failed_holdout`

## Evidence

### V26 True BTCUSDC Replay

- Gate passed: `False`
- Trades: `9768`
- Win rate: `0.137387`
- Total net pnl: `-84236.964807` bps
- Account return: `-6007.131692%`
- Failed checks: `win_rate;total_net_pnl;mean_net_pnl;no_loss_account_return;missed_trade_account_return;extra_cost_account_return;synthetic_loss_return;synthetic_loss_drawdown`

### V60 Design-Selected Sparse TP

- Rule: `reversal / 1080m / q0.99`
- Design trades/wins: `6/6`
- Holdout trades/wins: `12/12`
- Holdout total net pnl: `858.000000` bps

### V64 Holdout Dense Delay

- Passing delays: `111/121`
- Failing delays: `10`
- Worst delay by account return: `119`
- Worst account return: `6.079006%`

### V65 Signal Fragility

- Signals with loss: `3/12`
- Losing signal-delay rows: `15`
- Top fragile signal: `2026-02-03 18:47:00+00:00`
- Top fragile loss ranges: `109-110,112-113,116-120`
- Top fragile worst pnl: `-417.102573` bps

### V66 Design-Robust Selector

- Selected same as V60: `False`
- Selected rule: `reversal / 1440m / q0.99`
- Selected design pass count: `117/121`
- Selected holdout pass count: `0/121`
- Selected holdout fail ranges: `0-120`
- V60 reference holdout pass count: `111/121`
- V60 reference fail ranges: `5,109-110,112-113,116-120`

## Closure

The BTCUSDC sparse TP route is closed as not promotable under the current evidence. The route has historical pockets of success, but fails true replay, fails dense delay robustness, and the design-only robust selector does not produce a holdout-valid replacement.

## Files

- Summary JSON: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v67_btcusdc_sparse_tp_route_closure/v67_summary.json`
- Decision CSV: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v67_btcusdc_sparse_tp_route_closure/v67_sparse_tp_route_decision.csv`
- Source true replay: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v26_btcusdc_full_public_replay/summary.json`
- Source V64: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v64_btcusdc_sparse_tp_dense_delay_scan/v64_summary.json`
- Source V66: `/Users/jamie/Downloads/lob_microprice_lab_research_v26_btcusdc_contract_lock/runs/research_v66_btcusdc_sparse_tp_design_robust_selector/v66_summary.json`
