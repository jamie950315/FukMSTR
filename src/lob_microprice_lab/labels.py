from __future__ import annotations

import numpy as np
import pandas as pd

from .data_schema import timestamps_to_ns


def add_future_labels(features: pd.DataFrame, horizon_sec: float, threshold_bps: float) -> pd.DataFrame:
    """Add future mid, return bps, and direction label columns."""
    if "timestamp" not in features.columns or "mid" not in features.columns:
        raise ValueError("features must include timestamp and mid columns")

    out = features.sort_values("timestamp").reset_index(drop=True).copy()
    ts_ns = timestamps_to_ns(out["timestamp"])
    mid = out["mid"].astype(float).to_numpy()
    target_ts = ts_ns + int(float(horizon_sec) * 1_000_000_000)
    future_idx = np.searchsorted(ts_ns, target_ts, side="left")

    valid = future_idx < len(out)
    future_mid = np.full(len(out), np.nan, dtype=float)
    future_mid[valid] = mid[future_idx[valid]]
    out["future_mid"] = future_mid
    for col in ["best_bid", "best_ask"]:
        if col in out.columns:
            values = out[col].astype(float).to_numpy()
            future_values = np.full(len(out), np.nan, dtype=float)
            future_values[valid] = values[future_idx[valid]]
            out[f"future_{col}"] = future_values
    out["future_return_bps"] = (out["future_mid"] - out["mid"]) / out["mid"] * 10000.0

    label = np.zeros(len(out), dtype=int)
    ret = out["future_return_bps"].to_numpy()
    label[ret > threshold_bps] = 1
    label[ret < -threshold_bps] = -1
    out["label"] = label
    out = out.dropna(subset=["future_mid", "future_return_bps"]).reset_index(drop=True)
    return out
