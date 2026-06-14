from __future__ import annotations

import csv
import gzip
import io
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

import pandas as pd

TARDIS_DERIBIT_L2_SAMPLE_URL = (
    "https://datasets.tardis.dev/v1/deribit/incremental_book_L2/2020/04/01/BTC-PERPETUAL.csv.gz"
)
BINANCE_SPOT_DEPTH_URL = "https://data-api.binance.vision/api/v3/depth"


@dataclass
class ConversionStats:
    input_path: str
    output_path: str
    rows_read: int
    snapshots_written: int
    depth: int
    sample_ms: int
    first_timestamp: int | None
    last_timestamp: int | None
    crossed_or_empty_skips: int
    source_format: str = "tardis_incremental_book_L2"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def download_file(url: str, out_path: str | Path, overwrite: bool = False, chunk_size: int = 1 << 20) -> Path:
    """Download a public market-data file with a minimal stdlib dependency surface."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and not overwrite:
        return out

    tmp = out.with_suffix(out.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "lob-microprice-lab/0.2"})
    with urllib.request.urlopen(req, timeout=60) as response, tmp.open("wb") as f:
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
    tmp.replace(out)
    return out


def convert_tardis_incremental_l2_to_book_csv(
    input_path: str | Path,
    output_path: str | Path,
    *,
    depth: int = 10,
    sample_ms: int = 500,
    max_input_rows: int | None = None,
    max_snapshots: int | None = None,
) -> ConversionStats:
    """Reconstruct sampled top-N L2 snapshots from Tardis incremental_book_L2 CSV.

    Tardis incremental rows are price-level updates. Snapshot rows reset the local
    order book; non-snapshot rows apply deltas where amount == 0 removes a level.
    The output matches the package's normalized book schema:

    timestamp,bid_px_1,bid_sz_1,ask_px_1,ask_sz_1,...
    """
    if depth < 1:
        raise ValueError("depth must be >= 1")
    if sample_ms < 1:
        raise ValueError("sample_ms must be >= 1")

    inp = Path(input_path)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    bids: dict[float, float] = {}
    asks: dict[float, float] = {}
    rows_read = 0
    snapshots_written = 0
    first_ts: int | None = None
    last_ts: int | None = None
    next_sample_ts: int | None = None
    sample_us = int(sample_ms * 1000)
    crossed_or_empty_skips = 0
    active_snapshot_ts: int | None = None

    headers = ["timestamp"]
    for level in range(1, depth + 1):
        headers.extend([f"bid_px_{level}", f"bid_sz_{level}", f"ask_px_{level}", f"ask_sz_{level}"])

    def flush(ts_to_write: int) -> None:
        nonlocal snapshots_written, crossed_or_empty_skips, next_sample_ts
        if next_sample_ts is None or ts_to_write < next_sample_ts:
            return
        written = _write_book_snapshot(writer, ts_to_write, bids, asks, depth)
        if written:
            snapshots_written += 1
        else:
            crossed_or_empty_skips += 1
        next_sample_ts = ts_to_write + sample_us

    with _open_text_maybe_gzip(inp) as source, out.open("w", newline="", encoding="utf-8") as sink:
        reader = csv.DictReader(source)
        missing = {"timestamp", "is_snapshot", "side", "price", "amount"}.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Tardis file missing columns: {sorted(missing)}")
        writer = csv.writer(sink)
        writer.writerow(headers)

        current_ts: int | None = None
        for row in reader:
            rows_read += 1
            if max_input_rows is not None and rows_read > max_input_rows:
                break

            ts = int(float(row["timestamp"]))
            if current_ts is None:
                current_ts = ts
                first_ts = ts if first_ts is None else first_ts
                next_sample_ts = ts if next_sample_ts is None else next_sample_ts
            elif ts != current_ts:
                flush(current_ts)
                if max_snapshots is not None and snapshots_written >= max_snapshots:
                    break
                current_ts = ts
            last_ts = ts

            is_snapshot = _parse_bool(row["is_snapshot"])
            if is_snapshot and active_snapshot_ts != ts:
                # A Tardis snapshot consists of many rows sharing one timestamp.
                # Clear once at the beginning of each full-snapshot block.
                bids.clear()
                asks.clear()
                active_snapshot_ts = ts
            elif not is_snapshot:
                active_snapshot_ts = None
            side = str(row["side"]).strip().lower()
            price = float(row["price"])
            amount = float(row["amount"])
            if side == "bid":
                _apply_level(bids, price, amount)
            elif side == "ask":
                _apply_level(asks, price, amount)

        if current_ts is not None and (max_snapshots is None or snapshots_written < max_snapshots):
            flush(current_ts)

    stats = ConversionStats(
        input_path=str(inp),
        output_path=str(out),
        rows_read=int(rows_read),
        snapshots_written=int(snapshots_written),
        depth=int(depth),
        sample_ms=int(sample_ms),
        first_timestamp=first_ts,
        last_timestamp=last_ts,
        crossed_or_empty_skips=int(crossed_or_empty_skips),
    )
    out.with_suffix(out.suffix + ".stats.json").write_text(json.dumps(stats.to_dict(), indent=2), encoding="utf-8")
    return stats


def fetch_tardis_sample_book(
    out_dir: str | Path,
    *,
    url: str = TARDIS_DERIBIT_L2_SAMPLE_URL,
    depth: int = 10,
    sample_ms: int = 500,
    max_input_rows: int | None = None,
    max_snapshots: int | None = None,
    overwrite: bool = False,
) -> dict[str, object]:
    """Download the public Tardis sample and convert it into a model-ready book CSV."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    raw_path = out / "tardis_deribit_BTC-PERPETUAL_2020-04-01_incremental_book_L2.csv.gz"
    book_path = out / f"book_depth{depth}_{sample_ms}ms.csv"
    download_file(url, raw_path, overwrite=overwrite)
    stats = convert_tardis_incremental_l2_to_book_csv(
        raw_path,
        book_path,
        depth=depth,
        sample_ms=sample_ms,
        max_input_rows=max_input_rows,
        max_snapshots=max_snapshots,
    )
    manifest = {
        "source_url": url,
        "raw_path": str(raw_path),
        "book_path": str(book_path),
        "conversion": stats.to_dict(),
        "notes": [
            "This public sample is Deribit BTC-PERPETUAL L2 incremental order book data from Tardis.dev.",
            "No trade file is generated by this converter; trade-derived features are filled with zeros by the training pipeline.",
        ],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def fetch_binance_spot_depth_snapshots(
    output_path: str | Path,
    *,
    symbol: str = "BTCUSDT",
    depth: int = 20,
    interval_sec: float = 1.0,
    samples: int = 120,
) -> Path:
    """Poll Binance's public market-data-only depth endpoint into book CSV snapshots.

    This is intended for local smoke tests and small live captures. For gap-free
    reconstruction, use WebSocket diff-depth plus a REST seed snapshot.
    """
    if samples < 1:
        raise ValueError("samples must be >= 1")
    if depth not in {5, 10, 20, 50, 100, 500, 1000}:
        raise ValueError("Binance depth limit must be one of 5, 10, 20, 50, 100, 500, 1000")
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    headers = ["timestamp"]
    for level in range(1, depth + 1):
        headers.extend([f"bid_px_{level}", f"bid_sz_{level}", f"ask_px_{level}", f"ask_sz_{level}"])

    with out.open("w", newline="", encoding="utf-8") as sink:
        writer = csv.writer(sink)
        writer.writerow(headers)
        for i in range(samples):
            started = time.time()
            payload = _fetch_json(
                f"{BINANCE_SPOT_DEPTH_URL}?symbol={symbol.upper()}&limit={depth}",
                timeout=20,
            )
            timestamp_us = int(time.time() * 1_000_000)
            bids = [(float(px), float(sz)) for px, sz in payload.get("bids", [])[:depth]]
            asks = [(float(px), float(sz)) for px, sz in payload.get("asks", [])[:depth]]
            if len(bids) >= depth and len(asks) >= depth:
                row: list[object] = [timestamp_us]
                for j in range(depth):
                    row.extend([bids[j][0], bids[j][1], asks[j][0], asks[j][1]])
                writer.writerow(row)
            remaining = interval_sec - (time.time() - started)
            if i + 1 < samples and remaining > 0:
                time.sleep(remaining)
    return out


def _open_text_maybe_gzip(path: Path) -> io.TextIOBase:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", newline="", encoding="utf-8")
    return path.open("r", newline="", encoding="utf-8")


def _parse_bool(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "t", "yes", "y"}


def _apply_level(book_side: dict[float, float], price: float, amount: float) -> None:
    if amount <= 0:
        book_side.pop(price, None)
    else:
        book_side[price] = amount


def _write_book_snapshot(writer: csv.writer, ts: int, bids: dict[float, float], asks: dict[float, float], depth: int) -> bool:
    if not bids or not asks:
        return False
    top_bids = sorted(bids.items(), key=lambda kv: kv[0], reverse=True)[:depth]
    top_asks = sorted(asks.items(), key=lambda kv: kv[0])[:depth]
    if len(top_bids) < depth or len(top_asks) < depth:
        return False
    if top_bids[0][0] >= top_asks[0][0]:
        return False
    row: list[object] = [ts]
    for (bid_px, bid_sz), (ask_px, ask_sz) in zip(top_bids, top_asks):
        row.extend([bid_px, bid_sz, ask_px, ask_sz])
    writer.writerow(row)
    return True


def _fetch_json(url: str, timeout: int) -> dict[str, object]:
    req = urllib.request.Request(url, headers={"User-Agent": "lob-microprice-lab/0.2"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc
