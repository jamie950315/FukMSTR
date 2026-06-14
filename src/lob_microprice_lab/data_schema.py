from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


class SchemaError(ValueError):
    """Raised when input market data does not match the expected schema."""


def read_csv(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path)


def parse_timestamp_series(series: pd.Series) -> pd.Series:
    """Parse timestamps to timezone-aware UTC pandas timestamps.

    Numeric timestamps are interpreted by magnitude:
    - >= 1e18: nanoseconds
    - >= 1e15: microseconds
    - >= 1e12: milliseconds
    - otherwise: seconds
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series, utc=True)

    if pd.api.types.is_numeric_dtype(series):
        numeric = pd.to_numeric(series, errors="coerce")
        non_null = numeric.dropna()
        if non_null.empty:
            raise SchemaError("timestamp column contains no parseable values")
        median_abs = float(non_null.abs().median())
        if median_abs >= 1e18:
            unit = "ns"
        elif median_abs >= 1e15:
            unit = "us"
        elif median_abs >= 1e12:
            unit = "ms"
        else:
            unit = "s"
        return pd.to_datetime(numeric, unit=unit, utc=True)

    return pd.to_datetime(series, utc=True, errors="coerce")


def normalize_timestamp(df: pd.DataFrame, timestamp_col: str = "timestamp") -> pd.DataFrame:
    if timestamp_col not in df.columns:
        raise SchemaError(f"missing timestamp column: {timestamp_col}")
    out = df.copy()
    out["timestamp"] = parse_timestamp_series(out[timestamp_col])
    out = out.dropna(subset=["timestamp"]).sort_values("timestamp")
    out = out.drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)
    return out


def infer_depth(book: pd.DataFrame) -> int:
    depth = 0
    i = 1
    while True:
        cols = [f"bid_px_{i}", f"bid_sz_{i}", f"ask_px_{i}", f"ask_sz_{i}"]
        if all(c in book.columns for c in cols):
            depth = i
            i += 1
            continue
        break
    if depth == 0:
        raise SchemaError("book has no complete level columns: bid_px_1,bid_sz_1,ask_px_1,ask_sz_1")
    return depth


def validate_book(book: pd.DataFrame) -> int:
    depth = infer_depth(book)
    needed = ["timestamp"]
    for i in range(1, depth + 1):
        needed.extend([f"bid_px_{i}", f"bid_sz_{i}", f"ask_px_{i}", f"ask_sz_{i}"])
    missing = [c for c in needed if c not in book.columns]
    if missing:
        raise SchemaError(f"missing book columns: {missing}")
    return depth


def clean_book(book: pd.DataFrame, timestamp_col: str = "timestamp") -> pd.DataFrame:
    out = normalize_timestamp(book, timestamp_col=timestamp_col)
    depth = validate_book(out)

    numeric_cols: list[str] = []
    for i in range(1, depth + 1):
        numeric_cols.extend([f"bid_px_{i}", f"bid_sz_{i}", f"ask_px_{i}", f"ask_sz_{i}"])
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out.dropna(subset=["bid_px_1", "ask_px_1", "bid_sz_1", "ask_sz_1"])
    out = out[(out["bid_px_1"] > 0) & (out["ask_px_1"] > 0)]
    out = out[out["ask_px_1"] > out["bid_px_1"]]

    for i in range(1, depth + 1):
        out[f"bid_sz_{i}"] = out[f"bid_sz_{i}"].clip(lower=0)
        out[f"ask_sz_{i}"] = out[f"ask_sz_{i}"].clip(lower=0)
        out = out[(out[f"bid_px_{i}"] > 0) & (out[f"ask_px_{i}"] > 0)]

    out = out.replace([np.inf, -np.inf], np.nan).dropna(subset=["bid_px_1", "ask_px_1"])
    return out.reset_index(drop=True)


def normalize_trades(trades: pd.DataFrame | None, timestamp_col: str = "timestamp") -> pd.DataFrame | None:
    if trades is None:
        return None
    if trades.empty:
        return None
    needed = {timestamp_col, "price", "size", "side"}
    missing = needed.difference(trades.columns)
    if missing:
        raise SchemaError(f"missing trade columns: {sorted(missing)}")
    out = normalize_timestamp(trades, timestamp_col=timestamp_col)
    out["price"] = pd.to_numeric(out["price"], errors="coerce")
    out["size"] = pd.to_numeric(out["size"], errors="coerce")
    out = out.dropna(subset=["price", "size", "side"])
    out = out[(out["price"] > 0) & (out["size"] > 0)]
    out["side"] = out["side"].map(normalize_side)
    out = out.dropna(subset=["side"])
    return out.sort_values("timestamp").reset_index(drop=True)


def normalize_side(value: object) -> str | float:
    s = str(value).strip().lower()
    if s in {"buy", "b", "bid", "1", "+1", "true", "t"}:
        return "buy"
    if s in {"sell", "s", "ask", "-1", "false", "f"}:
        return "sell"
    return np.nan


def timestamps_to_ns(series: pd.Series) -> np.ndarray:
    try:
        parsed = pd.to_datetime(series, utc=True)
    except ValueError:
        # Pandas 2.x can fail when one CSV column mixes timestamps with and without fractional seconds.
        parsed = pd.to_datetime(series, utc=True, format="mixed")
    return parsed.to_numpy(dtype="datetime64[ns]").astype("int64")
