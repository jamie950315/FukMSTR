# Data schema

## Book snapshots

The feature pipeline expects one row per order book snapshot.

Required columns:

```text
timestamp
bid_px_1,bid_sz_1,ask_px_1,ask_sz_1
bid_px_2,bid_sz_2,ask_px_2,ask_sz_2
...
bid_px_N,bid_sz_N,ask_px_N,ask_sz_N
```

Rules:

- Level 1 is the best bid and best ask.
- Bid prices should be descending from best bid outward.
- Ask prices should be ascending from best ask outward.
- Sizes should be non-negative.
- Crossed or locked books are dropped by default because they break mid-price and spread features.
- Duplicate timestamps are sorted and only the final row is kept.

Recommended timestamp format:

```text
2026-01-01T00:00:00.000000000Z
```

Numeric timestamp support:

- seconds
- milliseconds
- microseconds
- nanoseconds

The loader uses magnitude heuristics for numeric timestamps. ISO-8601 is safer.

## Trades

Optional trade file columns:

```text
timestamp,price,size,side
```

Rules:

- `side` is aggressor side.
- Buy side means the trade consumed ask liquidity.
- Sell side means the trade consumed bid liquidity.
- Accepted buy values include `buy`, `b`, `1`, `true`.
- Accepted sell values include `sell`, `s`, `-1`, `false`.

## Minimal example

Book:

```csv
timestamp,bid_px_1,bid_sz_1,ask_px_1,ask_sz_1,bid_px_2,bid_sz_2,ask_px_2,ask_sz_2
2026-01-01T00:00:00Z,99.99,10,100.01,12,99.98,14,100.02,9
```

Trade:

```csv
timestamp,price,size,side
2026-01-01T00:00:00.100000Z,100.01,0.5,buy
```

## Real data adapters added in v0.2

### Tardis incremental L2 converter

Command:

```bash
lob-microprice-lab fetch-tardis-sample --out data/real_tardis --depth 10 --sample-ms 500 --max-snapshots 10000
```

Input schema expected by `convert-tardis-l2`:

```text
exchange,symbol,timestamp,local_timestamp,is_snapshot,side,price,amount
```

Rules:

- `is_snapshot=true` rows reset and rebuild the local book for their timestamp block.
- `is_snapshot=false` rows apply incremental price-level updates.
- `amount <= 0` removes the price level.
- `side` must be `bid` or `ask`.
- Output is sampled top-N depth in the normalized book CSV schema used by the rest of the package.
- The converter writes a sidecar `*.stats.json` file with input rows, snapshots written, depth, sample interval, and timestamp range.

### Binance public spot depth polling

Command:

```bash
lob-microprice-lab fetch-binance-depth --out data/binance/BTCUSDT_depth20.csv --symbol BTCUSDT --depth 20 --interval-sec 1 --samples 120
```

This polls Binance's public market-data depth endpoint and writes snapshots in the normalized book CSV schema. Use it for quick local smoke tests. It is sampled polling, so it is not a gap-free historical reconstruction.

### Binance public WebSocket local book capture

Command:

```bash
lob-microprice-lab collect-binance-ws --out data/binance/BTCUSDT_ws_depth20.csv --symbol BTCUSDT --depth 20 --sample-ms 1000 --seconds 120
```

This uses public market data only. It seeds a local order book from Binance REST depth, applies WebSocket diff-depth updates, and writes sampled top-N book snapshots in the normalized book CSV schema.

### Paper trading from captured book CSV

Command:

```bash
lob-microprice-lab paper-trade-v142 --out runs/paper_v142_book_csv --source book-csv --book-csv data/binance/BTCUSDT_ws_depth20.csv --ticks 10 --clean --no-sleep
```

The `book-csv` source reads `timestamp`, `bid_px_1`, and `ask_px_1`, then uses the level-1 midpoint as the paper-trading price. Rows with missing, non-positive, crossed, or locked level-1 prices are skipped.

## Paper dashboard state files

`paper-trade-v142` writes local paper-trading state for the dashboard:

```text
paper_events.jsonl
balance.csv
trades.csv
rejected_signals.csv
positions.csv
order_events.csv
decisions.csv
summary.json
paper_config.json
```

`positions.csv` is overwritten on each tick and represents current open paper positions. Important columns:

```text
snapshot_timestamp,signal_id,symbol,side,entry_timestamp,exit_due_timestamp,entry_price,mark_price,notional_usdc,unrealized_pnl_usdc,time_to_exit_minutes
```

`order_events.csv` is append-only and records paper order status:

```text
timestamp,signal_id,symbol,side,status,event_type,price,notional_usdc,reason,dry_run,order_type
```

Statuses include:

- `filled`: paper position opened.
- `closed`: paper position closed by scheduled exit.
- `closed_by_kill_switch`: paper position closed by the local dashboard kill switch.
- `rejected`: signal rejected before any paper position was opened.

`decisions.csv` is append-only and records why the system acted or did not act:

```text
timestamp,signal_id,symbol,side,decision,reason,direction_probability,snapshot_price,result
```

The dashboard kill switch writes `kill_switch.json`:

```json
{
  "active": true,
  "reason": "manual_dashboard",
  "requested_at": "2026-01-01T00:00:00Z",
  "scope": "paper_positions_only"
}
```

A running paper-trading loop reads this file and force-closes open paper positions at the next valid market snapshot. It does not place exchange orders.
