from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from lob_microprice_lab.real_data import convert_tardis_incremental_l2_to_book_csv


def test_convert_tardis_incremental_l2_to_book_csv(tmp_path: Path) -> None:
    raw = tmp_path / "tiny_tardis.csv"
    rows = [
        ["exchange", "symbol", "timestamp", "local_timestamp", "is_snapshot", "side", "price", "amount"],
        ["deribit", "BTC-PERPETUAL", "1000000", "1000000", "true", "bid", "99.5", "10"],
        ["deribit", "BTC-PERPETUAL", "1000000", "1000000", "true", "ask", "100.5", "12"],
        ["deribit", "BTC-PERPETUAL", "1500000", "1500000", "false", "bid", "100.0", "8"],
        ["deribit", "BTC-PERPETUAL", "2000000", "2000000", "false", "ask", "100.5", "0"],
        ["deribit", "BTC-PERPETUAL", "2000000", "2000000", "false", "ask", "100.25", "6"],
    ]
    with raw.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)

    out = tmp_path / "book.csv"
    stats = convert_tardis_incremental_l2_to_book_csv(raw, out, depth=1, sample_ms=500)
    book = pd.read_csv(out)

    assert stats.snapshots_written >= 2
    assert list(book.columns) == ["timestamp", "bid_px_1", "bid_sz_1", "ask_px_1", "ask_sz_1"]
    assert float(book.iloc[-1]["bid_px_1"]) == 100.0
    assert float(book.iloc[-1]["ask_px_1"]) == 100.25
