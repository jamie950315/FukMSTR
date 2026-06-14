from __future__ import annotations

import glob
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .data_schema import parse_timestamp_series


def parse_timeframe_seconds(value: str) -> float:
    """Parse compact candle timeframe strings such as 500ms, 1s, 5m, 1h."""
    text = str(value).strip().lower()
    if not text:
        raise ValueError("empty timeframe")
    units = [("ms", 0.001), ("s", 1.0), ("m", 60.0), ("h", 3600.0), ("d", 86400.0)]
    for suffix, multiplier in units:
        if text.endswith(suffix):
            number = text[: -len(suffix)].strip()
            if not number:
                raise ValueError(f"missing numeric part in timeframe: {value!r}")
            seconds = float(number) * multiplier
            if seconds <= 0:
                raise ValueError(f"timeframe must be positive: {value!r}")
            return seconds
    # Accept bare seconds for convenience.
    seconds = float(text)
    if seconds <= 0:
        raise ValueError(f"timeframe must be positive: {value!r}")
    return seconds


def sanitize_timeframe(value: str) -> str:
    text = str(value).strip().lower()
    if not text:
        raise ValueError("empty timeframe")
    out = []
    for ch in text:
        if ch.isalnum():
            out.append(ch)
        elif ch in {".", "-"}:
            out.append("p")
        else:
            out.append("_")
    return "".join(out)


@dataclass(frozen=True)
class KlineBuildResult:
    features: pd.DataFrame
    audit: dict[str, object]


def build_mid_candles_from_book(
    book: pd.DataFrame,
    *,
    timeframe: str,
    timestamp_col: str = "timestamp",
) -> pd.DataFrame:
    """Build OHLCV-like candles from book mid prices.

    The generated candles use the bar *open* timestamp in `timestamp` and expose a
    separate `close_ts`.  Downstream alignment only uses a candle when close_ts is
    not later than the event decision time, preventing open-bar leakage.
    """
    if timestamp_col not in book.columns:
        raise ValueError(f"book missing timestamp column: {timestamp_col}")
    frame = book.copy()
    ts = parse_timestamp_series(frame[timestamp_col])
    frame = frame.loc[ts.notna()].copy()
    frame[timestamp_col] = ts.loc[ts.notna()].to_numpy()
    if "mid" in frame.columns:
        mid = pd.to_numeric(frame["mid"], errors="coerce")
    elif {"best_bid", "best_ask"}.issubset(frame.columns):
        mid = (pd.to_numeric(frame["best_bid"], errors="coerce") + pd.to_numeric(frame["best_ask"], errors="coerce")) / 2.0
    elif {"bid_px_1", "ask_px_1"}.issubset(frame.columns):
        mid = (pd.to_numeric(frame["bid_px_1"], errors="coerce") + pd.to_numeric(frame["ask_px_1"], errors="coerce")) / 2.0
    else:
        raise ValueError("book must contain either mid, best_bid/best_ask, or bid_px_1/ask_px_1")
    frame = frame.assign(_mid=mid).dropna(subset=[timestamp_col, "_mid"]).sort_values(timestamp_col)
    if frame.empty:
        raise ValueError("no usable rows for candle construction")
    seconds = parse_timeframe_seconds(timeframe)
    freq = _seconds_to_pandas_freq(seconds)
    grouped = frame.set_index(timestamp_col)["_mid"].resample(freq, label="left", closed="left")
    candles = grouped.agg(open="first", high="max", low="min", close="last")
    candles["volume"] = grouped.count().astype(float)
    candles = candles.dropna(subset=["open", "high", "low", "close"]).reset_index()
    candles = candles.rename(columns={timestamp_col: "timestamp"})
    candles["close_ts"] = pd.to_datetime(candles["timestamp"], utc=True) + pd.to_timedelta(seconds, unit="s")
    candles["source"] = "book_mid"
    candles["timeframe"] = str(timeframe)
    return candles[["timestamp", "close_ts", "open", "high", "low", "close", "volume", "source", "timeframe"]]


def load_candle_files(
    paths: Iterable[str | Path],
    *,
    timeframe: str,
    timestamp_col: str = "timestamp",
) -> pd.DataFrame:
    """Load external OHLCV candles from one or more CSV/CSV.GZ files.

    Accepted timestamp aliases: timestamp, open_time, open_ts, start_time,
    date, datetime.  If close_ts/end_time is absent, close_ts is inferred as
    open timestamp plus the timeframe.
    """
    expanded: list[str] = []
    for path in paths:
        matches = glob.glob(str(path))
        expanded.extend(matches if matches else [str(path)])
    if not expanded:
        raise ValueError("no candle paths provided")
    frames: list[pd.DataFrame] = []
    for path in expanded:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(str(p))
        frame = pd.read_csv(p)
        frame.columns = [str(c).strip() for c in frame.columns]
        rename: dict[str, str] = {}
        lower = {c.lower(): c for c in frame.columns}
        for alias in [timestamp_col, "timestamp", "open_time", "open_ts", "start_time", "date", "datetime"]:
            if alias.lower() in lower:
                rename[lower[alias.lower()]] = "timestamp"
                break
        for canonical, aliases in {
            "open": ["open", "o"],
            "high": ["high", "h"],
            "low": ["low", "l"],
            "close": ["close", "c"],
            "volume": ["volume", "vol", "v", "base_volume"],
            "close_ts": ["close_ts", "close_time", "end_time", "end_ts"],
        }.items():
            for alias in aliases:
                if alias.lower() in lower:
                    rename[lower[alias.lower()]] = canonical
                    break
        frame = frame.rename(columns=rename)
        missing = {"timestamp", "open", "high", "low", "close"}.difference(frame.columns)
        if missing:
            raise ValueError(f"candle file {p} missing required columns: {sorted(missing)}")
        if "volume" not in frame.columns:
            frame["volume"] = 0.0
        frame = frame[[c for c in ["timestamp", "close_ts", "open", "high", "low", "close", "volume"] if c in frame.columns]].copy()
        frame["timestamp"] = parse_timestamp_series(frame["timestamp"])
        if "close_ts" in frame.columns:
            frame["close_ts"] = parse_timestamp_series(frame["close_ts"])
        else:
            frame["close_ts"] = frame["timestamp"] + pd.to_timedelta(parse_timeframe_seconds(timeframe), unit="s")
        for col in ["open", "high", "low", "close", "volume"]:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
        frame = frame.dropna(subset=["timestamp", "close_ts", "open", "high", "low", "close"]).copy()
        frame["source"] = str(p)
        frame["timeframe"] = str(timeframe)
        frames.append(frame)
    out = pd.concat(frames, ignore_index=True).sort_values("timestamp")
    out = out.drop_duplicates(subset=["timestamp", "close_ts"], keep="last").reset_index(drop=True)
    return out[["timestamp", "close_ts", "open", "high", "low", "close", "volume", "source", "timeframe"]]


def build_kline_feature_frame(
    events: pd.DataFrame,
    *,
    book: pd.DataFrame | None = None,
    candle_paths_by_timeframe: dict[str, list[str | Path]] | None = None,
    timeframes: list[str] | None = None,
    timestamp_col: str = "timestamp",
    decision_lag_sec: float = 0.0,
    lookbacks: list[int] | None = None,
    fillna_value: float = 0.0,
) -> KlineBuildResult:
    """Build leakage-safe multi-timeframe candle features aligned to event rows.

    Alignment rule: a candle may influence an event only when
    candle.close_ts <= event.timestamp - decision_lag_sec.
    """
    if timestamp_col not in events.columns:
        raise ValueError(f"events missing timestamp column: {timestamp_col}")
    timeframes = [str(x).strip() for x in (timeframes or []) if str(x).strip()]
    candle_paths_by_timeframe = candle_paths_by_timeframe or {}
    for tf in candle_paths_by_timeframe:
        if tf not in timeframes:
            timeframes.append(tf)
    if not timeframes:
        raise ValueError("at least one kline timeframe is required")
    lookbacks = sorted({int(x) for x in (lookbacks or [1, 3, 6, 12, 24]) if int(x) > 0})
    event_ts = parse_timestamp_series(events[timestamp_col])
    if event_ts.isna().any():
        raise ValueError("events contain unparseable timestamps")
    left = pd.DataFrame({timestamp_col: event_ts})
    left["_event_order"] = np.arange(len(left))
    left["_available_ts"] = left[timestamp_col] - pd.to_timedelta(float(decision_lag_sec), unit="s")
    left_sorted = left.sort_values("_available_ts")

    out = pd.DataFrame({timestamp_col: event_ts})
    audit: dict[str, object] = {
        "timeframes": timeframes,
        "decision_lag_sec": float(decision_lag_sec),
        "lookbacks": lookbacks,
        "rows": int(len(events)),
        "ok": True,
        "violations": {},
        "missing_rate_by_timeframe": {},
        "max_overrun_ns": 0,
        "feature_columns": [],
    }
    feature_cols: list[str] = []
    for tf in timeframes:
        if tf in candle_paths_by_timeframe and candle_paths_by_timeframe[tf]:
            candles = load_candle_files(candle_paths_by_timeframe[tf], timeframe=tf, timestamp_col=timestamp_col)
        else:
            if book is None:
                raise ValueError(f"no book or candle files available for timeframe {tf}")
            candles = build_mid_candles_from_book(book, timeframe=tf, timestamp_col=timestamp_col)
        candle_features = _decorate_candles(candles, timeframe=tf, lookbacks=lookbacks)
        prefix = f"kline_{sanitize_timeframe(tf)}_"
        right = candle_features.sort_values("close_ts").copy()
        aligned = pd.merge_asof(
            left_sorted,
            right,
            left_on="_available_ts",
            right_on="close_ts",
            direction="backward",
            allow_exact_matches=True,
        )
        aligned = aligned.sort_values("_event_order").reset_index(drop=True)
        close_ts = pd.to_datetime(aligned["close_ts"], utc=True, errors="coerce")
        available_ts = pd.to_datetime(aligned["_available_ts"], utc=True, errors="coerce")
        overrun = (close_ts.astype("int64") - available_ts.astype("int64")).where(close_ts.notna(), -1)
        max_overrun = int(overrun.max()) if len(overrun) else 0
        if max_overrun > 0:
            audit["ok"] = False
            audit["violations"][tf] = int(max_overrun)
        audit["max_overrun_ns"] = max(int(audit["max_overrun_ns"]), max(0, max_overrun))
        audit["missing_rate_by_timeframe"][tf] = float(close_ts.isna().mean())
        age_sec = (parse_timestamp_series(left[timestamp_col]).reset_index(drop=True) - close_ts.reset_index(drop=True)).dt.total_seconds()
        out[f"{prefix}age_sec"] = age_sec.astype(float)
        numeric_cols = [c for c in right.columns if c not in {"timestamp", "close_ts", "source", "timeframe"}]
        for col in numeric_cols:
            values = pd.to_numeric(aligned[col], errors="coerce").reset_index(drop=True).astype(float)
            name = f"{prefix}{col}"
            out[name] = values
            feature_cols.append(name)
        feature_cols.append(f"{prefix}age_sec")
    for col in feature_cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(float(fillna_value))
    audit["feature_columns"] = [c for c in feature_cols if c in out.columns]
    audit["feature_count"] = int(len(audit["feature_columns"]))
    return KlineBuildResult(features=out, audit=audit)


def append_kline_features(
    dataset: pd.DataFrame,
    *,
    book: pd.DataFrame | None = None,
    candle_paths_by_timeframe: dict[str, list[str | Path]] | None = None,
    timeframes: list[str] | None = None,
    timestamp_col: str = "timestamp",
    decision_lag_sec: float = 0.0,
    lookbacks: list[int] | None = None,
) -> KlineBuildResult:
    result = build_kline_feature_frame(
        dataset[[timestamp_col]].copy(),
        book=book,
        candle_paths_by_timeframe=candle_paths_by_timeframe,
        timeframes=timeframes,
        timestamp_col=timestamp_col,
        decision_lag_sec=decision_lag_sec,
        lookbacks=lookbacks,
    )
    merged = dataset.reset_index(drop=True).copy()
    features = result.features.drop(columns=[timestamp_col], errors="ignore").reset_index(drop=True)
    merged = pd.concat([merged, features], axis=1)
    return KlineBuildResult(features=merged, audit=result.audit)


def write_kline_cache(
    *,
    events: pd.DataFrame,
    out_path: str | Path,
    book: pd.DataFrame | None = None,
    candle_paths_by_timeframe: dict[str, list[str | Path]] | None = None,
    timeframes: list[str] | None = None,
    timestamp_col: str = "timestamp",
    decision_lag_sec: float = 0.0,
    lookbacks: list[int] | None = None,
) -> dict[str, object]:
    result = build_kline_feature_frame(
        events,
        book=book,
        candle_paths_by_timeframe=candle_paths_by_timeframe,
        timeframes=timeframes,
        timestamp_col=timestamp_col,
        decision_lag_sec=decision_lag_sec,
        lookbacks=lookbacks,
    )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    result.features.to_csv(out, index=False)
    audit_path = out.with_suffix(out.suffix + ".audit.json")
    audit_path.write_text(json.dumps(result.audit, indent=2), encoding="utf-8")
    return {"out": str(out), "audit": result.audit, "audit_path": str(audit_path)}


def parse_candle_path_specs(specs: list[str] | None) -> dict[str, list[str]]:
    """Parse CLI specs of the form timeframe:path or timeframe:path1,path2."""
    out: dict[str, list[str]] = {}
    for raw in specs or []:
        if not str(raw).strip():
            continue
        if ":" not in raw:
            raise ValueError(f"candle spec must be timeframe:path, got {raw!r}")
        tf, paths = raw.split(":", 1)
        tf = tf.strip()
        values = [p.strip() for p in paths.split(",") if p.strip()]
        if not tf or not values:
            raise ValueError(f"invalid candle spec: {raw!r}")
        out.setdefault(tf, []).extend(values)
    return out


def _decorate_candles(candles: pd.DataFrame, *, timeframe: str, lookbacks: list[int]) -> pd.DataFrame:
    c = candles.copy().sort_values("close_ts").reset_index(drop=True)
    for col in ["open", "high", "low", "close", "volume"]:
        c[col] = pd.to_numeric(c[col], errors="coerce")
    close = c["close"].replace(0, np.nan).astype(float)
    open_ = c["open"].replace(0, np.nan).astype(float)
    high = c["high"].astype(float)
    low = c["low"].astype(float)
    volume = c["volume"].astype(float).clip(lower=0)
    denom = close.abs().replace(0, np.nan)
    c["range_bps"] = (high - low) / denom * 10000.0
    c["body_bps"] = (close - open_) / open_.abs().replace(0, np.nan) * 10000.0
    upper = high - np.maximum(open_, close)
    lower = np.minimum(open_, close) - low
    c["upper_wick_bps"] = upper / denom * 10000.0
    c["lower_wick_bps"] = lower / denom * 10000.0
    rng = (high - low).replace(0, np.nan)
    c["close_pos"] = ((close - low) / rng - 0.5).clip(-0.5, 0.5)
    c["direction"] = np.sign(close - open_)
    c["volume_log"] = np.log1p(volume)
    c["ret_1_bps"] = close.pct_change(1) * 10000.0
    abs_ret_1 = c["ret_1_bps"].abs()
    for lb in lookbacks:
        c[f"ret_{lb}_bps"] = close.pct_change(lb) * 10000.0
        c[f"mom_{lb}_bps"] = (close - close.shift(lb)) / close.shift(lb).abs().replace(0, np.nan) * 10000.0
        c[f"rv_{lb}_bps"] = np.sqrt((c["ret_1_bps"].fillna(0.0) ** 2).rolling(lb, min_periods=1).sum())
        ma = close.rolling(lb, min_periods=1).mean()
        c[f"ma_gap_{lb}_bps"] = (close - ma) / ma.abs().replace(0, np.nan) * 10000.0
        c[f"range_z_{lb}"] = _rolling_z(c["range_bps"], lb)
        c[f"volume_z_{lb}"] = _rolling_z(c["volume_log"], lb)
        c[f"trend_eff_{lb}"] = (c[f"ret_{lb}_bps"] / abs_ret_1.rolling(lb, min_periods=1).sum().replace(0, np.nan)).clip(-5, 5)
    # A bounded deterministic per-timeframe signal.  It is not a fitted model;
    # kline_weighting.py learns the fold-local weights on calibration data.
    short_lb = min([lb for lb in lookbacks if lb >= 1], default=1)
    mid_lb = min([lb for lb in lookbacks if lb >= 3], default=short_lb)
    long_lb = min([lb for lb in lookbacks if lb >= 6], default=mid_lb)
    signal = (
        0.30 * np.tanh(c.get(f"ret_{short_lb}_bps", c["ret_1_bps"]).fillna(0.0) / 6.0)
        + 0.30 * np.tanh(c.get(f"mom_{mid_lb}_bps", c["ret_1_bps"]).fillna(0.0) / 10.0)
        + 0.25 * np.tanh(c.get(f"ma_gap_{long_lb}_bps", c["ret_1_bps"]).fillna(0.0) / 8.0)
        + 0.15 * c["close_pos"].fillna(0.0) * 2.0
    )
    c["signal"] = pd.Series(signal).clip(-1.0, 1.0)
    keep = ["timestamp", "close_ts", "open", "high", "low", "close", "volume", "range_bps", "body_bps", "upper_wick_bps", "lower_wick_bps", "close_pos", "direction", "volume_log", "signal"]
    for lb in lookbacks:
        keep.extend([
            f"ret_{lb}_bps",
            f"mom_{lb}_bps",
            f"rv_{lb}_bps",
            f"ma_gap_{lb}_bps",
            f"range_z_{lb}",
            f"volume_z_{lb}",
            f"trend_eff_{lb}",
        ])
    return c[[col for col in keep if col in c.columns]]


def _rolling_z(series: pd.Series, window: int) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    mean = s.rolling(window, min_periods=1).mean()
    min_periods = 2 if int(window) >= 2 else 1
    std = s.rolling(window, min_periods=min_periods).std(ddof=0).replace(0, np.nan)
    return ((s - mean) / std).replace([np.inf, -np.inf], np.nan).fillna(0.0).clip(-10, 10)


def _seconds_to_pandas_freq(seconds: float) -> str:
    if abs(seconds - round(seconds)) < 1e-9:
        sec = int(round(seconds))
        if sec % 86400 == 0:
            return f"{sec // 86400}D"
        if sec % 3600 == 0:
            return f"{sec // 3600}h"
        if sec % 60 == 0:
            return f"{sec // 60}min"
        return f"{sec}s"
    ms = int(round(seconds * 1000.0))
    if ms <= 0:
        raise ValueError(f"invalid seconds: {seconds}")
    return f"{ms}ms"
