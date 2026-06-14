from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .btc_contract_data import parse_binance_public_zip


def build_btcusdc_public_kline_replay_ledger(
    *,
    template_ledger: pd.DataFrame,
    kline_paths: list[str | Path],
    out_path: str | Path,
    horizon_sec: float = 90.0,
    latency_sec: float = 0.5,
    taker_roundtrip_fee_bps: float = 8.0,
    spread_bps: float = 0.0,
) -> pd.DataFrame:
    """Build a BTCUSDC ledger from real Binance public kline paths.

    This is a public candle replay, not an L2 order-book replay. It keeps the
    frozen template's event time-of-day, side, and take-profit settings, then
    prices those events on BTCUSDC candles.
    """

    if template_ledger.empty:
        raise ValueError("template_ledger is empty")
    if not kline_paths:
        raise ValueError("kline_paths is empty")

    template = template_ledger.copy().reset_index(drop=True)
    template_ts = pd.to_datetime(template["timestamp"], utc=True)
    midnight = template_ts.dt.normalize()
    offsets = (template_ts - midnight).dt.total_seconds().to_numpy(float)

    rows: list[dict[str, object]] = []
    for day_idx, path in enumerate(kline_paths, start=1):
        klines = _load_kline_path(path)
        if klines.empty:
            continue
        klines = klines.sort_values("timestamp").reset_index(drop=True)
        day_start = pd.Timestamp(klines["timestamp"].iloc[0]).normalize()
        ts = pd.to_datetime(klines["timestamp"], utc=True)
        ts_ns = ts.to_numpy(dtype="datetime64[ns]").astype("int64")
        open_px = pd.to_numeric(klines["open"], errors="coerce").to_numpy(float)
        high_px = pd.to_numeric(klines["high"], errors="coerce").to_numpy(float)
        low_px = pd.to_numeric(klines["low"], errors="coerce").to_numpy(float)
        close_px = pd.to_numeric(klines["close"], errors="coerce").to_numpy(float)

        for template_idx, template_row in template.iterrows():
            signal = int(np.clip(int(template_row.get("signal", 0)), -1, 1))
            if signal == 0:
                continue
            decision_ts = day_start + pd.to_timedelta(float(offsets[template_idx]), unit="s")
            entry_target = decision_ts + pd.to_timedelta(float(latency_sec), unit="s")
            exit_target = decision_ts + pd.to_timedelta(float(horizon_sec), unit="s")
            entry_idx = int(np.searchsorted(ts_ns, entry_target.to_datetime64().astype("datetime64[ns]").astype("int64"), side="left"))
            exit_idx = int(np.searchsorted(ts_ns, exit_target.to_datetime64().astype("datetime64[ns]").astype("int64"), side="left"))
            if entry_idx >= len(klines) or exit_idx >= len(klines) or exit_idx <= entry_idx:
                continue

            tp_bps = float(template_row.get("take_profit_bps", 0.0) or 0.0)
            entry_mid = float(open_px[entry_idx])
            if not np.isfinite(entry_mid) or entry_mid <= 0:
                continue
            half_spread = float(spread_bps) / 20000.0
            if signal > 0:
                entry_px = entry_mid * (1.0 + half_spread)
                horizon_exit = float(close_px[exit_idx]) * (1.0 - half_spread)
                take_profit_px = entry_px * (1.0 + tp_bps / 10000.0) if tp_bps > 0 else np.inf
                exit_px, exit_reason, exit_bar = _long_exit(high_px, close_px, entry_idx, exit_idx, take_profit_px, horizon_exit)
                gross = (exit_px - entry_px) / entry_px * 10000.0
            else:
                entry_px = entry_mid * (1.0 - half_spread)
                horizon_exit = float(close_px[exit_idx]) * (1.0 + half_spread)
                take_profit_px = entry_px * (1.0 - tp_bps / 10000.0) if tp_bps > 0 else -np.inf
                exit_px, exit_reason, exit_bar = _short_exit(low_px, close_px, entry_idx, exit_idx, take_profit_px, horizon_exit)
                gross = (entry_px - exit_px) / entry_px * 10000.0
            if not np.isfinite(exit_px) or exit_px <= 0:
                continue
            net = float(gross) - float(taker_roundtrip_fee_bps)
            best_bid = entry_mid * (1.0 - half_spread)
            best_ask = entry_mid * (1.0 + half_spread)
            row = {
                "timestamp": decision_ts.isoformat(),
                "best_bid": best_bid,
                "best_ask": best_ask,
                "signal": signal,
                "fold": int(template_row.get("fold", ((day_idx - 1) % 5) + 1)),
                "raw_selective_signal": signal,
                "traded": 1,
                "entry_px_taker": float(entry_px),
                "exit_px_taker": float(exit_px),
                "latency_sec": float(latency_sec),
                "gross_pnl_bps": float(gross),
                "cost_bps": float(taker_roundtrip_fee_bps),
                "net_pnl_bps": net,
                "exit_reason": exit_reason,
                "hold_sec": float((int(ts_ns[exit_bar]) - int(ts_ns[entry_idx])) / 1_000_000_000.0),
                "take_profit_bps": tp_bps,
                "stop_loss_bps": float(template_row.get("stop_loss_bps", 0.0) or 0.0),
                "reserve_horizon": bool(template_row.get("reserve_horizon", True)),
                "real_taker_fee_bps_per_side": float(taker_roundtrip_fee_bps) / 2.0,
                "real_maker_fee_bps_per_side": 0.0,
                "real_roundtrip_fee_bps": float(taker_roundtrip_fee_bps),
                "symbol": "BTCUSDC",
                "data_mode": "true_btcusdc_public_kline_replay",
                "source_symbol": "BTCUSDC Binance USD-M public klines",
                "template_timestamp": str(template_row.get("timestamp", "")),
                "template_row": int(template_idx),
                "replay_date": day_start.date().isoformat(),
                "kline_interval": _infer_interval_label(path),
                "kline_path": str(path),
            }
            for col in [
                "prob_down",
                "prob_flat",
                "prob_up",
                "prob_edge",
                "kline_blend_alpha",
                "v24_core_lane",
                "v24_rescue_lane",
            ]:
                if col in template.columns:
                    row[col] = template_row.get(col)
            rows.append(row)

    ledger = pd.DataFrame(rows)
    if not ledger.empty:
        ledger["equity_bps"] = pd.to_numeric(ledger["net_pnl_bps"], errors="coerce").fillna(0.0).cumsum()
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(out, index=False)
    return ledger


def _load_kline_path(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() == ".zip":
        interval = _infer_interval_label(path)
        return parse_binance_public_zip(path, data_type="klines", interval=interval)
    df = pd.read_csv(path)
    required = {"timestamp", "open", "high", "low", "close"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"kline file missing columns: {sorted(missing)}")
    out = df.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    return out


def _infer_interval_label(path: str | Path) -> str:
    name = Path(path).name
    parts = name.split("-")
    return parts[1] if len(parts) >= 3 else ""


def _long_exit(
    high_px: np.ndarray,
    close_px: np.ndarray,
    entry_idx: int,
    exit_idx: int,
    take_profit_px: float,
    horizon_exit: float,
) -> tuple[float, str, int]:
    for j in range(entry_idx + 1, exit_idx + 1):
        if np.isfinite(take_profit_px) and float(high_px[j]) >= take_profit_px:
            return float(take_profit_px), "take_profit", j
    return float(horizon_exit), "horizon", exit_idx


def _short_exit(
    low_px: np.ndarray,
    close_px: np.ndarray,
    entry_idx: int,
    exit_idx: int,
    take_profit_px: float,
    horizon_exit: float,
) -> tuple[float, str, int]:
    for j in range(entry_idx + 1, exit_idx + 1):
        if np.isfinite(take_profit_px) and float(low_px[j]) <= take_profit_px:
            return float(take_profit_px), "take_profit", j
    return float(horizon_exit), "horizon", exit_idx
