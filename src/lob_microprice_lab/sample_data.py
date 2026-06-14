from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def generate_sample_data(out_dir: str | Path, rows: int = 4000, depth: int = 10, seed: int = 42) -> tuple[Path, Path]:
    """Generate synthetic L2 book and trade files with mild predictive structure."""
    if rows < 200:
        raise ValueError("rows must be at least 200")
    if depth < 1:
        raise ValueError("depth must be at least 1")

    rng = np.random.default_rng(seed)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    timestamps = pd.date_range("2026-01-01T00:00:00Z", periods=rows, freq="200ms")
    latent = np.zeros(rows)
    for i in range(1, rows):
        latent[i] = 0.92 * latent[i - 1] + rng.normal(0, 0.35)

    returns = 0.0008 * latent + rng.normal(0, 0.006, size=rows)
    mid = 100.0 + np.cumsum(returns)
    spread = np.maximum(0.02, 0.02 + rng.normal(0, 0.002, size=rows))
    best_bid = mid - spread / 2
    best_ask = mid + spread / 2

    book: dict[str, object] = {"timestamp": _format_timestamps(timestamps)}
    tick = 0.01
    for level in range(1, depth + 1):
        distance = (level - 1) * tick
        book[f"bid_px_{level}"] = best_bid - distance
        book[f"ask_px_{level}"] = best_ask + distance
        base = 20.0 + 8.0 * np.exp(-0.2 * level)
        bid_size = rng.lognormal(mean=np.log(base), sigma=0.35, size=rows) * np.exp(0.22 * latent)
        ask_size = rng.lognormal(mean=np.log(base), sigma=0.35, size=rows) * np.exp(-0.22 * latent)
        if level in {1, 2}:
            shock_idx = rng.choice(rows, size=max(1, rows // 80), replace=False)
            bid_size[shock_idx] *= rng.uniform(3.0, 8.0, size=len(shock_idx))
            ask_size[shock_idx] *= rng.uniform(3.0, 8.0, size=len(shock_idx))
        book[f"bid_sz_{level}"] = bid_size
        book[f"ask_sz_{level}"] = ask_size

    book_df = pd.DataFrame(book)
    book_path = out / "book.csv"
    book_df.to_csv(book_path, index=False)

    trade_rows = max(100, int(rows * 0.7))
    trade_indices = np.sort(rng.choice(np.arange(rows), size=trade_rows, replace=True))
    jitter_ns = rng.integers(0, 180_000_000, size=trade_rows)
    trade_ts = timestamps[trade_indices] + pd.to_timedelta(jitter_ns, unit="ns")
    side_prob_buy = 1.0 / (1.0 + np.exp(-latent[trade_indices]))
    is_buy = rng.random(trade_rows) < side_prob_buy
    trade_price = np.where(is_buy, best_ask[trade_indices], best_bid[trade_indices])
    trade_size = rng.lognormal(mean=0.0, sigma=0.8, size=trade_rows)
    trades_df = pd.DataFrame(
        {
            "timestamp": _format_timestamps(trade_ts),
            "price": trade_price,
            "size": trade_size,
            "side": np.where(is_buy, "buy", "sell"),
        }
    ).sort_values("timestamp")
    trades_path = out / "trades.csv"
    trades_df.to_csv(trades_path, index=False)
    return book_path, trades_path


def _format_timestamps(values) -> list[str]:
    series = pd.Series(pd.to_datetime(values, utc=True))
    return series.dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ").tolist()
