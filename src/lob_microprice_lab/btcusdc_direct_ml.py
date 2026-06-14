from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


def _rolling_min_periods(window: int) -> int:
    window = int(window)
    if window <= 0:
        raise ValueError("window must be positive")
    return min(window, max(1, window // 4))


def build_direct_ml_features(
    bars: pd.DataFrame,
    *,
    lookbacks: Iterable[int] = (1, 2, 3, 5, 10, 15, 30, 60, 120, 240, 480, 720, 1440),
) -> tuple[pd.DataFrame, list[str]]:
    required = {"timestamp", "high", "low", "close", "volume", "taker_buy_base_volume"}
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"bars missing columns: {sorted(missing)}")

    source = bars.copy()
    source["timestamp"] = pd.to_datetime(source["timestamp"], utc=True)
    source = source.sort_values("timestamp").reset_index(drop=True)
    close = pd.to_numeric(source["close"], errors="coerce")
    high = pd.to_numeric(source["high"], errors="coerce")
    low = pd.to_numeric(source["low"], errors="coerce")
    volume = pd.to_numeric(source["volume"], errors="coerce").replace(0, np.nan)
    taker_buy = pd.to_numeric(source["taker_buy_base_volume"], errors="coerce")

    features = pd.DataFrame({"timestamp": source["timestamp"], "close": close})
    for lookback in lookbacks:
        lb = int(lookback)
        min_periods = _rolling_min_periods(lb)
        ret = close.pct_change(lb) * 10000.0
        features[f"ret_{lb}"] = ret
        features[f"absret_mean_{lb}"] = ret.abs().rolling(lb, min_periods=min_periods).mean()
        features[f"vol_ratio_{lb}"] = volume / volume.rolling(lb, min_periods=min_periods).mean()

    features["range_bps"] = (high - low) / close * 10000.0
    features["taker_imbalance"] = (2.0 * taker_buy / volume - 1.0).replace([np.inf, -np.inf], np.nan)
    for lookback in [5, 15, 60, 240, 720]:
        min_periods = _rolling_min_periods(lookback)
        features[f"taker_imb_mean_{lookback}"] = features["taker_imbalance"].rolling(lookback, min_periods=min_periods).mean()
        features[f"range_mean_{lookback}"] = features["range_bps"].rolling(lookback, min_periods=min_periods).mean()

    features["hour"] = features["timestamp"].dt.hour
    features["dow"] = features["timestamp"].dt.dayofweek
    feature_cols = [c for c in features.columns if c not in {"timestamp", "close"}]
    features[feature_cols] = features[feature_cols].replace([np.inf, -np.inf], np.nan)
    return features, feature_cols


def run_prequential_gate_selection(
    candidates: pd.DataFrame,
    *,
    warmup_folds: int,
    min_history_active: int | None = None,
) -> tuple[pd.DataFrame, dict[str, float | int]]:
    required = {"config", "fold", "active", "validation_total", "validation_trades"}
    missing = required.difference(candidates.columns)
    if missing:
        raise ValueError(f"candidates missing columns: {sorted(missing)}")

    min_active = int(min_history_active) if min_history_active is not None else max(1, int(warmup_folds) // 2)
    rows: list[dict[str, object]] = []
    folds = sorted(pd.to_numeric(candidates["fold"], errors="raise").astype(int).unique().tolist())
    for fold in folds:
        if fold <= int(warmup_folds):
            continue
        history = candidates.loc[pd.to_numeric(candidates["fold"], errors="coerce").astype(int) < fold]
        grouped = (
            history.groupby("config")
            .agg(
                total=("validation_total", "sum"),
                active=("active", "sum"),
                min_val=("validation_total", "min"),
                trades=("validation_trades", "sum"),
            )
            .reset_index()
        )
        grouped = grouped.loc[pd.to_numeric(grouped["active"], errors="coerce") >= min_active]
        if grouped.empty:
            rows.append({"fold": int(fold), "config": "risk_off", "active": False, "validation_total": 0.0, "validation_trades": 0})
            continue
        best = grouped.sort_values(["total", "min_val", "active"], ascending=[False, False, False]).iloc[0]
        current = candidates.loc[(pd.to_numeric(candidates["fold"], errors="coerce").astype(int) == fold) & (candidates["config"] == best["config"])]
        if current.empty:
            rows.append({"fold": int(fold), "config": str(best["config"]), "active": False, "validation_total": 0.0, "validation_trades": 0})
            continue
        row = current.iloc[0]
        rows.append(
            {
                "fold": int(fold),
                "config": str(best["config"]),
                "active": bool(row["active"]),
                "validation_total": float(row["validation_total"]) if bool(row["active"]) else 0.0,
                "validation_trades": int(row["validation_trades"]) if bool(row["active"]) else 0,
            }
        )

    selected = pd.DataFrame(rows)
    active = selected.loc[selected["active"].astype(bool)] if not selected.empty else selected
    summary: dict[str, float | int] = {
        "warmup": int(warmup_folds),
        "folds": int(len(selected)),
        "active": int(len(active)),
        "passed": int((pd.to_numeric(active.get("validation_total", pd.Series(dtype=float)), errors="coerce") > 0).sum()) if len(active) else 0,
        "total": float(pd.to_numeric(selected.get("validation_total", pd.Series(dtype=float)), errors="coerce").sum()) if len(selected) else 0.0,
        "min": float(pd.to_numeric(active.get("validation_total", pd.Series(dtype=float)), errors="coerce").min()) if len(active) else 0.0,
        "median": float(pd.to_numeric(active.get("validation_total", pd.Series(dtype=float)), errors="coerce").median()) if len(active) else 0.0,
        "trades": int(pd.to_numeric(selected.get("validation_trades", pd.Series(dtype=float)), errors="coerce").sum()) if len(selected) else 0,
    }
    return selected, summary
