from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from pandas.errors import PerformanceWarning

warnings.filterwarnings("ignore", category=PerformanceWarning)

from .config import FeatureConfig
from .data_schema import clean_book, infer_depth, normalize_trades, timestamps_to_ns


def safe_div(numerator: pd.Series | np.ndarray, denominator: pd.Series | np.ndarray) -> pd.Series | np.ndarray:
    return np.where(np.asarray(denominator) != 0, np.asarray(numerator) / np.asarray(denominator), 0.0)


def signed_log1p(values: pd.Series | np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    return np.sign(arr) * np.log1p(np.abs(arr))


def build_features(
    book: pd.DataFrame,
    trades: pd.DataFrame | None = None,
    cfg: FeatureConfig | None = None,
    timestamp_col: str = "timestamp",
) -> pd.DataFrame:
    """Build model-ready features from book snapshots and optional trades.

    The feature set intentionally stays tabular so that small local experiments can run with scikit-learn. It includes
    classical LOB state variables, microprice variants, order-flow imbalance, and short rolling dynamics.
    """
    cfg = cfg or FeatureConfig()
    book = clean_book(book, timestamp_col=timestamp_col)
    trades = normalize_trades(trades, timestamp_col=timestamp_col) if trades is not None else None
    depth = infer_depth(book)
    max_requested = max(cfg.depth_levels) if cfg.depth_levels else depth
    max_level = min(depth, max_requested)
    levels = [level for level in cfg.depth_levels if level <= depth]
    if not levels:
        levels = [1]

    f = pd.DataFrame({"timestamp": book["timestamp"]})
    f["best_bid"] = book["bid_px_1"].astype(float)
    f["best_ask"] = book["ask_px_1"].astype(float)
    f["mid"] = (f["best_bid"] + f["best_ask"]) / 2.0
    f["spread"] = f["best_ask"] - f["best_bid"]
    f["spread_bps"] = f["spread"] / f["mid"] * 10000.0

    bid1 = book["bid_sz_1"].astype(float).clip(lower=0)
    ask1 = book["ask_sz_1"].astype(float).clip(lower=0)
    denom1 = bid1 + ask1
    f["microprice_l1"] = safe_div(f["best_ask"] * bid1 + f["best_bid"] * ask1, denom1)
    f["microprice_dev_bps"] = (f["microprice_l1"] - f["mid"]) / f["mid"] * 10000.0
    f["weighted_mid_l1"] = safe_div(f["best_bid"] * bid1 + f["best_ask"] * ask1, denom1)
    f["weighted_mid_dev_bps"] = (f["weighted_mid_l1"] - f["mid"]) / f["mid"] * 10000.0

    # Per-level raw shape features.
    for i in range(1, max_level + 1):
        bid_px = book[f"bid_px_{i}"].astype(float)
        ask_px = book[f"ask_px_{i}"].astype(float)
        bid_sz = book[f"bid_sz_{i}"].astype(float).clip(lower=0)
        ask_sz = book[f"ask_sz_{i}"].astype(float).clip(lower=0)
        f[f"bid_sz_l{i}_log"] = np.log1p(bid_sz)
        f[f"ask_sz_l{i}_log"] = np.log1p(ask_sz)
        f[f"level_size_imb_l{i}"] = safe_div(bid_sz - ask_sz, bid_sz + ask_sz)
        f[f"bid_distance_bps_l{i}"] = (f["mid"] - bid_px) / f["mid"] * 10000.0
        f[f"ask_distance_bps_l{i}"] = (ask_px - f["mid"]) / f["mid"] * 10000.0
        f[f"level_width_bps_l{i}"] = (ask_px - bid_px) / f["mid"] * 10000.0

    # Cumulative depth, VWAP distance, and higher-rank microprice features.
    cumulative: dict[int, tuple[pd.Series, pd.Series]] = {}
    for n in levels:
        bid_depth = sum(book[f"bid_sz_{i}"].astype(float).clip(lower=0) for i in range(1, n + 1))
        ask_depth = sum(book[f"ask_sz_{i}"].astype(float).clip(lower=0) for i in range(1, n + 1))
        cumulative[n] = (bid_depth, ask_depth)
        f[f"bid_depth_l{n}"] = bid_depth
        f[f"ask_depth_l{n}"] = ask_depth
        f[f"bid_depth_l{n}_log"] = np.log1p(bid_depth)
        f[f"ask_depth_l{n}_log"] = np.log1p(ask_depth)
        f[f"depth_ratio_l{n}_log"] = np.log1p(bid_depth) - np.log1p(ask_depth)
        f[f"imbalance_l{n}"] = safe_div(bid_depth - ask_depth, bid_depth + ask_depth)
        f[f"imbalance_x_spread_l{n}"] = f[f"imbalance_l{n}"] * f["spread_bps"]

        bid_notional = sum(book[f"bid_px_{i}"].astype(float) * book[f"bid_sz_{i}"].astype(float).clip(lower=0) for i in range(1, n + 1))
        ask_notional = sum(book[f"ask_px_{i}"].astype(float) * book[f"ask_sz_{i}"].astype(float).clip(lower=0) for i in range(1, n + 1))
        bid_vwap = safe_div(bid_notional, bid_depth)
        ask_vwap = safe_div(ask_notional, ask_depth)
        f[f"bid_vwap_distance_bps_l{n}"] = (f["mid"] - bid_vwap) / f["mid"] * 10000.0
        f[f"ask_vwap_distance_bps_l{n}"] = (ask_vwap - f["mid"]) / f["mid"] * 10000.0
        f[f"vwap_pressure_l{n}"] = f[f"ask_vwap_distance_bps_l{n}"] - f[f"bid_vwap_distance_bps_l{n}"]

        if cfg.add_multi_level_microprice:
            micro = safe_div(ask_vwap * bid_depth + bid_vwap * ask_depth, bid_depth + ask_depth)
            f[f"microprice_l{n}"] = micro
            f[f"microprice_dev_bps_l{n}"] = (micro - f["mid"]) / f["mid"] * 10000.0

    if cfg.add_depth_shape_features:
        f = add_depth_shape_features(f, book, levels=levels)

    if cfg.add_order_flow_features:
        f = add_order_flow_features(f, book, max_level=max_level, levels=levels)

    if trades is not None and not trades.empty:
        trade_features = build_trade_features(f["timestamp"], trades, cfg.trade_windows_sec)
        f = pd.concat([f, trade_features], axis=1)
    else:
        for window in cfg.trade_windows_sec:
            key = _window_key(window)
            f[f"trade_count_{key}"] = 0.0
            f[f"trade_buy_size_{key}"] = 0.0
            f[f"trade_sell_size_{key}"] = 0.0
            f[f"trade_imbalance_{key}"] = 0.0
            f[f"trade_total_size_{key}_log"] = 0.0

    if cfg.add_lagged_features:
        f = add_temporal_features(f, cfg.ewm_span, windows_rows=cfg.temporal_windows_rows)

    f = f.replace([np.inf, -np.inf], np.nan)
    return f.dropna(subset=["mid", "spread_bps"]).reset_index(drop=True)


def add_depth_shape_features(frame: pd.DataFrame, book: pd.DataFrame, levels: list[int]) -> pd.DataFrame:
    f = frame.copy()
    for n in levels:
        if n <= 1:
            continue
        bid_top = book["bid_sz_1"].astype(float).clip(lower=0)
        ask_top = book["ask_sz_1"].astype(float).clip(lower=0)
        bid_tail = sum(book[f"bid_sz_{i}"].astype(float).clip(lower=0) for i in range(2, n + 1))
        ask_tail = sum(book[f"ask_sz_{i}"].astype(float).clip(lower=0) for i in range(2, n + 1))
        bid_depth = bid_top + bid_tail
        ask_depth = ask_top + ask_tail
        f[f"bid_top_concentration_l{n}"] = safe_div(bid_top, bid_depth)
        f[f"ask_top_concentration_l{n}"] = safe_div(ask_top, ask_depth)
        f[f"top_concentration_gap_l{n}"] = f[f"bid_top_concentration_l{n}"] - f[f"ask_top_concentration_l{n}"]
        f[f"tail_imbalance_l{n}"] = safe_div(bid_tail - ask_tail, bid_tail + ask_tail)

        bid_px_n = book[f"bid_px_{n}"].astype(float)
        ask_px_n = book[f"ask_px_{n}"].astype(float)
        f[f"book_width_bps_l{n}"] = (ask_px_n - bid_px_n) / f["mid"] * 10000.0
        f[f"depth_per_bps_l{n}_log"] = np.log1p(bid_depth + ask_depth) - np.log1p(f[f"book_width_bps_l{n}"].clip(lower=0))
    return f


def add_order_flow_features(frame: pd.DataFrame, book: pd.DataFrame, max_level: int, levels: list[int]) -> pd.DataFrame:
    f = frame.copy()
    level_ofi: dict[int, np.ndarray] = {}
    for i in range(1, max_level + 1):
        bid_px = book[f"bid_px_{i}"].astype(float)
        ask_px = book[f"ask_px_{i}"].astype(float)
        bid_sz = book[f"bid_sz_{i}"].astype(float).clip(lower=0)
        ask_sz = book[f"ask_sz_{i}"].astype(float).clip(lower=0)
        prev_bid_px = bid_px.shift(1)
        prev_ask_px = ask_px.shift(1)
        prev_bid_sz = bid_sz.shift(1)
        prev_ask_sz = ask_sz.shift(1)

        # Cont-style signed queue change. A bid price improvement adds demand; an ask price improvement adds supply.
        e_bid = np.where(
            bid_px > prev_bid_px,
            bid_sz,
            np.where(bid_px == prev_bid_px, bid_sz - prev_bid_sz, -prev_bid_sz),
        )
        e_ask = np.where(
            ask_px < prev_ask_px,
            ask_sz,
            np.where(ask_px == prev_ask_px, ask_sz - prev_ask_sz, -prev_ask_sz),
        )
        ofi = np.nan_to_num(e_bid - e_ask, nan=0.0, posinf=0.0, neginf=0.0)
        level_ofi[i] = ofi
        f[f"ofi_l{i}"] = ofi
        f[f"ofi_l{i}_signed_log"] = signed_log1p(ofi)
        depth = bid_sz + ask_sz
        f[f"ofi_norm_l{i}"] = safe_div(ofi, depth)

    for n in levels:
        used = [level_ofi[i] for i in range(1, min(n, max_level) + 1)]
        if not used:
            continue
        arr = np.vstack(used)
        total = arr.sum(axis=0)
        f[f"ofi_sum_l{n}"] = total
        f[f"ofi_sum_l{n}_signed_log"] = signed_log1p(total)
        bid_depth = frame.get(f"bid_depth_l{n}", pd.Series(0.0, index=frame.index))
        ask_depth = frame.get(f"ask_depth_l{n}", pd.Series(0.0, index=frame.index))
        f[f"ofi_sum_l{n}_norm"] = safe_div(total, bid_depth + ask_depth)
    return f


def build_trade_features(book_timestamps: pd.Series, trades: pd.DataFrame, windows_sec: list[float]) -> pd.DataFrame:
    trades = trades.sort_values("timestamp").reset_index(drop=True)
    trade_ns = timestamps_to_ns(trades["timestamp"])
    book_ns = timestamps_to_ns(book_timestamps)

    buy_size = np.where(trades["side"].to_numpy() == "buy", trades["size"].astype(float).to_numpy(), 0.0)
    sell_size = np.where(trades["side"].to_numpy() == "sell", trades["size"].astype(float).to_numpy(), 0.0)
    count = np.ones(len(trades), dtype=float)

    c_buy = np.concatenate([[0.0], np.cumsum(buy_size)])
    c_sell = np.concatenate([[0.0], np.cumsum(sell_size)])
    c_count = np.concatenate([[0.0], np.cumsum(count)])

    out: dict[str, np.ndarray] = {}
    for window in windows_sec:
        key = _window_key(window)
        span_ns = int(float(window) * 1_000_000_000)
        right = np.searchsorted(trade_ns, book_ns, side="right")
        left = np.searchsorted(trade_ns, book_ns - span_ns, side="left")
        buy = c_buy[right] - c_buy[left]
        sell = c_sell[right] - c_sell[left]
        cnt = c_count[right] - c_count[left]
        out[f"trade_count_{key}"] = cnt
        out[f"trade_buy_size_{key}"] = buy
        out[f"trade_sell_size_{key}"] = sell
        denom = buy + sell
        out[f"trade_imbalance_{key}"] = np.divide(buy - sell, denom, out=np.zeros_like(denom), where=denom != 0)
        out[f"trade_total_size_{key}_log"] = np.log1p(buy + sell)
    return pd.DataFrame(out)


def add_temporal_features(frame: pd.DataFrame, ewm_span: int, windows_rows: list[int] | None = None) -> pd.DataFrame:
    windows_rows = windows_rows or [2, 5, 10, 20]
    base_cols = [
        "spread_bps",
        "microprice_dev_bps",
        "microprice_dev_bps_l3",
        "microprice_dev_bps_l5",
        "microprice_dev_bps_l10",
        "imbalance_l1",
        "imbalance_l3",
        "imbalance_l5",
        "imbalance_l10",
        "ofi_sum_l1_norm",
        "ofi_sum_l3_norm",
        "ofi_sum_l5_norm",
        "ofi_sum_l10_norm",
        "trade_imbalance_1s",
        "trade_imbalance_5s",
        "trade_imbalance_10s",
    ]
    extra: dict[str, pd.Series | np.ndarray] = {}
    for col in base_cols:
        if col not in frame.columns:
            continue
        extra[f"{col}_diff1"] = frame[col].diff().fillna(0.0)
        extra[f"{col}_ewm"] = frame[col].ewm(span=ewm_span, adjust=False).mean()
        for window in windows_rows:
            if window <= 1:
                continue
            extra[f"{col}_mean_{window}r"] = frame[col].rolling(window=window, min_periods=1).mean()
            extra[f"{col}_diff_{window}r"] = (frame[col] - frame[col].shift(window)).fillna(0.0)

    mid_ret_1 = frame["mid"].pct_change().fillna(0.0) * 10000.0
    extra["mid_ret_1r_bps"] = mid_ret_1
    for window in windows_rows:
        if window <= 1:
            continue
        ret = frame["mid"].pct_change(periods=window).fillna(0.0) * 10000.0
        extra[f"mid_ret_{window}r_bps"] = ret
        extra[f"mid_vol_{window}r_bps"] = mid_ret_1.rolling(window=window, min_periods=2).std().fillna(0.0)
        extra[f"spread_z_{window}r"] = _rolling_z(frame["spread_bps"], window)
    if not extra:
        return frame
    return pd.concat([frame, pd.DataFrame(extra, index=frame.index)], axis=1)


def _rolling_z(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window=window, min_periods=2).mean()
    std = series.rolling(window=window, min_periods=2).std()
    z = (series - mean) / std.replace(0, np.nan)
    return z.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _window_key(window: float) -> str:
    if float(window).is_integer():
        return f"{int(window)}s"
    raw = str(window).replace(".", "p")
    return f"{raw}s"
