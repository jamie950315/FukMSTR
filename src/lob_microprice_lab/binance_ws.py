from __future__ import annotations

import asyncio
import csv
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BINANCE_REST_DEPTH_URL = "https://api.binance.com/api/v3/depth"
BINANCE_WS_BASE = "wss://stream.binance.com:9443/ws"


@dataclass
class BinanceLocalOrderBook:
    symbol: str
    depth: int = 20
    bids: dict[float, float] = field(default_factory=dict)
    asks: dict[float, float] = field(default_factory=dict)
    last_update_id: int | None = None

    def load_snapshot(self, payload: dict[str, Any]) -> None:
        self.last_update_id = int(payload["lastUpdateId"])
        self.bids = {float(px): float(sz) for px, sz in payload.get("bids", []) if float(sz) > 0}
        self.asks = {float(px): float(sz) for px, sz in payload.get("asks", []) if float(sz) > 0}

    def apply_depth_event(self, event: dict[str, Any]) -> bool:
        """Apply one Binance diff-depth event.

        Returns True when the event was applied. Returns False for old events. Raises RuntimeError when a sequence gap is
        detected and the local book needs a fresh REST snapshot.
        """
        if self.last_update_id is None:
            raise RuntimeError("snapshot is not loaded")
        first_id = int(event["U"])
        final_id = int(event["u"])
        if final_id <= self.last_update_id:
            return False
        if first_id > self.last_update_id + 1:
            raise RuntimeError(f"depth stream gap: first={first_id}, expected<={self.last_update_id + 1}")
        for px, sz in event.get("b", []):
            _apply_level(self.bids, float(px), float(sz))
        for px, sz in event.get("a", []):
            _apply_level(self.asks, float(px), float(sz))
        self.last_update_id = final_id
        return True

    def row(self, timestamp_us: int | None = None) -> list[object] | None:
        if timestamp_us is None:
            timestamp_us = int(time.time() * 1_000_000)
        bids = sorted(((px, sz) for px, sz in self.bids.items() if sz > 0), reverse=True)[: self.depth]
        asks = sorted((px, sz) for px, sz in self.asks.items() if sz > 0)[: self.depth]
        if len(bids) < self.depth or len(asks) < self.depth:
            return None
        if bids[0][0] >= asks[0][0]:
            return None
        out: list[object] = [timestamp_us]
        for i in range(self.depth):
            out.extend([bids[i][0], bids[i][1], asks[i][0], asks[i][1]])
        return out


def fetch_rest_depth(symbol: str, limit: int) -> dict[str, Any]:
    query = urllib.parse.urlencode({"symbol": symbol.upper(), "limit": int(limit)})
    req = urllib.request.Request(f"{BINANCE_REST_DEPTH_URL}?{query}", headers={"User-Agent": "lob-microprice-lab/0.3"})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


async def collect_binance_spot_local_book_async(
    output_path: str | Path,
    *,
    symbol: str = "BTCUSDT",
    depth: int = 20,
    sample_ms: int = 1000,
    seconds: float = 120.0,
    rest_limit: int = 1000,
) -> Path:
    """Collect a gap-checked Binance spot local order book using REST snapshot + diff-depth WebSocket."""
    try:
        import websockets
    except ImportError as exc:
        raise RuntimeError("collect-binance-ws requires the 'websockets' package") from exc

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    book = BinanceLocalOrderBook(symbol=symbol.upper(), depth=int(depth))
    sample_ns = int(float(sample_ms) * 1_000_000)
    next_sample = time.time_ns()
    end_time = time.time() + float(seconds)
    stream = f"{symbol.lower()}@depth@100ms"
    url = f"{BINANCE_WS_BASE}/{stream}"

    headers = ["timestamp"]
    for level in range(1, depth + 1):
        headers.extend([f"bid_px_{level}", f"bid_sz_{level}", f"ask_px_{level}", f"ask_sz_{level}"])

    with out.open("w", newline="", encoding="utf-8") as sink:
        writer = csv.writer(sink)
        writer.writerow(headers)
        async with websockets.connect(url, ping_interval=20, ping_timeout=20, max_queue=2000) as ws:
            # Buffer events while getting the snapshot, then apply the first event that bridges the snapshot ID.
            buffered: list[dict[str, Any]] = []
            snapshot = fetch_rest_depth(symbol.upper(), rest_limit)
            book.load_snapshot(snapshot)
            while time.time() < end_time:
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
                event = json.loads(raw)
                if int(event["u"]) <= int(book.last_update_id or 0):
                    continue
                try:
                    book.apply_depth_event(event)
                except RuntimeError:
                    snapshot = fetch_rest_depth(symbol.upper(), rest_limit)
                    book.load_snapshot(snapshot)
                    buffered.clear()
                    continue
                now_ns = time.time_ns()
                if now_ns >= next_sample:
                    row = book.row(timestamp_us=now_ns // 1000)
                    if row is not None:
                        writer.writerow(row)
                    while next_sample <= now_ns:
                        next_sample += sample_ns
    return out


def collect_binance_spot_local_book(
    output_path: str | Path,
    *,
    symbol: str = "BTCUSDT",
    depth: int = 20,
    sample_ms: int = 1000,
    seconds: float = 120.0,
    rest_limit: int = 1000,
) -> Path:
    return asyncio.run(
        collect_binance_spot_local_book_async(
            output_path,
            symbol=symbol,
            depth=depth,
            sample_ms=sample_ms,
            seconds=seconds,
            rest_limit=rest_limit,
        )
    )


def _apply_level(book: dict[float, float], price: float, size: float) -> None:
    if size <= 0:
        book.pop(price, None)
    else:
        book[price] = size
