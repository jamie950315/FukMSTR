from __future__ import annotations

import json
import math
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .backtest import summarize_trades
from .data_schema import timestamps_to_ns
from .stress import block_bootstrap_pnl


@dataclass(frozen=True)
class SelectiveCandidate:
    """Concrete, calibration-derived selective trading rule.

    The model still determines direction from probability edge.  This candidate only gates when that
    model signal is allowed to trade.  Every threshold in this object must be derived from a past
    calibration window before it is applied to a future validation fold.
    """

    edge_threshold: float
    direction_mode: str = "normal"  # normal, invert
    signed_col: str | None = None
    signed_mode: str = "none"  # none, agree, disagree
    signed_abs_threshold: float = 0.0
    spread_max_bps: float | None = None
    vol_col: str | None = None
    vol_mode: str = "none"  # none, low, high, band
    vol_min: float | None = None
    vol_max: float | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "SelectiveCandidate":
        allowed = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in payload.items() if k in allowed})


DEFAULT_SIGNED_COLUMNS = [
    "imbalance_l3",
    "imbalance_l5",
    "imbalance_l10",
    "microprice_dev_bps_l3",
    "microprice_dev_bps_l5",
    "microprice_dev_bps_l10",
    "ofi_sum_l3_norm",
    "ofi_sum_l5_norm",
    "ofi_sum_l10_norm",
    "mid_ret_60r_bps",
    "mid_ret_90r_bps",
    "mid_ret_120r_bps",
]

DEFAULT_VOL_COLUMNS = ["mid_vol_60r_bps", "mid_vol_90r_bps", "mid_vol_120r_bps"]


def build_selective_signals(frame: pd.DataFrame, candidate: SelectiveCandidate) -> pd.Series:
    """Create long/short/flat signals from current-row information only."""
    _assert_no_future_filter(candidate)
    edge = frame.get("prob_up", 0.0).astype(float) - frame.get("prob_down", 0.0).astype(float)
    if candidate.direction_mode == "invert":
        edge = -edge
    elif candidate.direction_mode != "normal":
        raise ValueError(f"unsupported direction_mode: {candidate.direction_mode}")
    signal = np.where(edge >= candidate.edge_threshold, 1, np.where(edge <= -candidate.edge_threshold, -1, 0)).astype(int)
    mask = signal != 0

    if candidate.signed_col and candidate.signed_mode != "none" and candidate.signed_col in frame.columns:
        signed = pd.to_numeric(frame[candidate.signed_col], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        threshold = float(candidate.signed_abs_threshold or 0.0)
        directional = signal * signed
        if candidate.signed_mode == "agree":
            mask &= directional >= threshold
        elif candidate.signed_mode == "disagree":
            mask &= directional <= -threshold
        else:
            raise ValueError(f"unsupported signed_mode: {candidate.signed_mode}")

    if candidate.spread_max_bps is not None and "spread_bps" in frame.columns:
        spread = pd.to_numeric(frame["spread_bps"], errors="coerce").fillna(np.inf).to_numpy(dtype=float)
        mask &= spread <= float(candidate.spread_max_bps)

    if candidate.vol_col and candidate.vol_mode != "none" and candidate.vol_col in frame.columns:
        vol = pd.to_numeric(frame[candidate.vol_col], errors="coerce").fillna(np.nan).to_numpy(dtype=float)
        if candidate.vol_mode == "low":
            mask &= vol <= float(candidate.vol_max)
        elif candidate.vol_mode == "high":
            mask &= vol >= float(candidate.vol_min)
        elif candidate.vol_mode == "band":
            mask &= (vol >= float(candidate.vol_min)) & (vol <= float(candidate.vol_max))
        else:
            raise ValueError(f"unsupported vol_mode: {candidate.vol_mode}")

    return pd.Series(np.where(mask, signal, 0), index=frame.index, name="signal")


def backtest_selective_taker_bidask_non_overlapping(
    predictions: pd.DataFrame,
    *,
    candidate: SelectiveCandidate,
    cost_bps: float,
    horizon_sec: float,
    latency_sec: float = 0.0,
    timestamp_col: str = "timestamp",
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Backtest a selective candidate with conservative taker bid/ask execution."""
    signals = build_selective_signals(predictions, candidate)
    return backtest_fixed_signals_taker_bidask_non_overlapping(
        predictions.assign(signal=signals),
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
        timestamp_col=timestamp_col,
        candidate=candidate,
    )


def backtest_fixed_signals_taker_bidask_non_overlapping(
    predictions: pd.DataFrame,
    *,
    cost_bps: float,
    horizon_sec: float,
    latency_sec: float = 0.0,
    timestamp_col: str = "timestamp",
    candidate: SelectiveCandidate | None = None,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Reprice a precomputed signal column under a cost/latency setting.

    This lets a calibration-selected rule be stress-tested without reselecting the rule.
    """
    required = {timestamp_col, "best_bid", "best_ask", "signal"}
    missing = required.difference(predictions.columns)
    if missing:
        raise ValueError(f"prediction frame missing columns for fixed-signal bid/ask execution: {sorted(missing)}")
    if latency_sec < 0:
        raise ValueError("latency_sec must be non-negative")

    out = predictions.copy().sort_values(timestamp_col).reset_index(drop=True)
    raw = out["signal"].fillna(0).astype(int).clip(-1, 1).to_numpy(dtype=int)
    ts_ns = timestamps_to_ns(out[timestamp_col])
    bid = out["best_bid"].astype(float).to_numpy()
    ask = out["best_ask"].astype(float).to_numpy()
    horizon_ns = int(float(horizon_sec) * 1_000_000_000)
    latency_ns = int(float(latency_sec) * 1_000_000_000)

    entry_target = ts_ns + latency_ns
    exit_target = ts_ns + horizon_ns
    entry_idx = np.searchsorted(ts_ns, entry_target, side="left")
    exit_idx = np.searchsorted(ts_ns, exit_target, side="left")
    valid = (entry_idx < len(out)) & (exit_idx < len(out)) & (entry_target < exit_target)

    kept = np.zeros(len(out), dtype=int)
    entry_px = np.full(len(out), np.nan, dtype=float)
    exit_px = np.full(len(out), np.nan, dtype=float)
    gross = np.zeros(len(out), dtype=float)
    next_allowed = -np.inf

    for i, (sig, ts) in enumerate(zip(raw, ts_ns)):
        if sig == 0 or ts < next_allowed or not valid[i]:
            continue
        ei = int(entry_idx[i])
        xi = int(exit_idx[i])
        if sig > 0:
            ep = ask[ei]
            xp = bid[xi]
            pnl = (xp - ep) / ep * 10000.0
        else:
            ep = bid[ei]
            xp = ask[xi]
            pnl = (ep - xp) / ep * 10000.0
        if not (np.isfinite(ep) and np.isfinite(xp) and ep > 0 and xp > 0):
            continue
        kept[i] = int(sig)
        entry_px[i] = float(ep)
        exit_px[i] = float(xp)
        gross[i] = float(pnl)
        next_allowed = int(ts) + horizon_ns

    out["raw_selective_signal"] = raw
    out["signal"] = kept
    out["traded"] = (out["signal"] != 0).astype(int)
    out["entry_px_taker"] = entry_px
    out["exit_px_taker"] = exit_px
    out["latency_sec"] = float(latency_sec)
    out["gross_pnl_bps"] = gross
    out["cost_bps"] = out["traded"] * float(cost_bps)
    out["net_pnl_bps"] = out["gross_pnl_bps"] - out["cost_bps"]
    out.loc[out["traded"] == 0, ["gross_pnl_bps", "cost_bps", "net_pnl_bps"]] = 0.0
    out["equity_bps"] = out["net_pnl_bps"].cumsum()
    metrics = summarize_trades(out)
    metrics.update(
        {
            "mode": "selective_taker_bidask_non_overlap",
            "cost_bps": float(cost_bps),
            "horizon_sec": float(horizon_sec),
            "latency_sec": float(latency_sec),
        }
    )
    if candidate is not None:
        metrics.update(_candidate_metric_fields(candidate))
    return out, metrics


def generate_candidate_grid(
    calibration: pd.DataFrame,
    *,
    edge_thresholds: Iterable[float],
    signed_columns: Iterable[str] | None = None,
    signed_abs_quantiles: Iterable[float] = (0.0, 0.5, 0.75),
    signed_modes: Iterable[str] = ("agree", "disagree"),
    spread_quantiles: Iterable[float] = (1.0, 0.75, 0.5),
    vol_modes: Iterable[str] = ("none", "low", "high", "band"),
    direction_modes: Iterable[str] = ("normal", "invert"),
) -> list[SelectiveCandidate]:
    """Materialize candidates using calibration quantiles only."""
    signed_columns = [c for c in (signed_columns or DEFAULT_SIGNED_COLUMNS) if c in calibration.columns and not c.startswith("future_")]
    vol_col = next((c for c in DEFAULT_VOL_COLUMNS if c in calibration.columns and not c.startswith("future_")), None)
    edges = [float(x) for x in edge_thresholds]
    directions = [str(x).strip() for x in direction_modes if str(x).strip()]
    candidates: list[SelectiveCandidate] = []

    spread_thresholds: list[float | None] = []
    if "spread_bps" in calibration.columns:
        spread_values = pd.to_numeric(calibration["spread_bps"], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        for q in spread_quantiles:
            q = float(q)
            spread_thresholds.append(None if q >= 1.0 or spread_values.empty else float(spread_values.quantile(q)))
    else:
        spread_thresholds = [None]
    spread_thresholds = _dedupe_optional_floats(spread_thresholds)

    vol_specs: list[tuple[str | None, str, float | None, float | None]] = [(None, "none", None, None)]
    if vol_col:
        vol_values = pd.to_numeric(calibration[vol_col], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        if not vol_values.empty:
            q20 = float(vol_values.quantile(0.20))
            q50 = float(vol_values.quantile(0.50))
            q75 = float(vol_values.quantile(0.75))
            q80 = float(vol_values.quantile(0.80))
            requested = set(vol_modes)
            if "low" in requested:
                vol_specs.append((vol_col, "low", None, q75))
            if "high" in requested:
                vol_specs.append((vol_col, "high", q50, None))
            if "band" in requested:
                vol_specs.append((vol_col, "band", q20, q80))

    for edge in edges:
        for direction in directions:
            for spread_max in spread_thresholds:
                for vcol, vmode, vmin, vmax in vol_specs:
                    candidates.append(SelectiveCandidate(edge_threshold=edge, direction_mode=direction, spread_max_bps=spread_max, vol_col=vcol, vol_mode=vmode, vol_min=vmin, vol_max=vmax))

            for col in signed_columns:
                abs_values = pd.to_numeric(calibration[col], errors="coerce").abs().replace([np.inf, -np.inf], np.nan).dropna()
                if abs_values.empty or abs_values.nunique() <= 1:
                    continue
                thresholds = [float(abs_values.quantile(float(q))) for q in signed_abs_quantiles]
                thresholds = _dedupe_floats(thresholds)
                for mode in signed_modes:
                    for threshold in thresholds:
                        for spread_max in spread_thresholds:
                            for vcol, vmode, vmin, vmax in vol_specs:
                                candidates.append(
                                    SelectiveCandidate(
                                        edge_threshold=edge,
                                        direction_mode=direction,
                                        signed_col=col,
                                        signed_mode=mode,
                                        signed_abs_threshold=threshold,
                                        spread_max_bps=spread_max,
                                        vol_col=vcol,
                                        vol_mode=vmode,
                                        vol_min=vmin,
                                        vol_max=vmax,
                                    )
                                )
    return candidates


def search_selective_candidates(
    calibration: pd.DataFrame,
    *,
    edge_thresholds: list[float],
    cost_bps: float,
    horizon_sec: float,
    latency_sec: float,
    min_trades: int,
    signed_columns: list[str] | None = None,
    max_candidates: int | None = None,
    spread_quantiles: list[float] | None = None,
    vol_modes: list[str] | None = None,
) -> pd.DataFrame:
    candidates = generate_candidate_grid(
        calibration,
        edge_thresholds=edge_thresholds,
        signed_columns=signed_columns,
        spread_quantiles=spread_quantiles or [1.0, 0.75, 0.5],
        vol_modes=vol_modes or ["none", "low", "high", "band"],
    )
    if max_candidates is not None:
        candidates = candidates[: int(max_candidates)]
    rows: list[dict[str, object]] = []
    for idx, candidate in enumerate(candidates):
        _, metrics = backtest_selective_taker_bidask_non_overlapping(
            calibration,
            candidate=candidate,
            cost_bps=cost_bps,
            horizon_sec=horizon_sec,
            latency_sec=latency_sec,
        )
        row = {"candidate_id": idx, **_candidate_metric_fields(candidate), **metrics, "candidate_json": json.dumps(candidate.to_dict(), sort_keys=True)}
        rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["meets_min_trades"] = out["trades"].astype(float) >= float(min_trades)
    out["rank_score"] = (
        out["mean_net_pnl_bps"].astype(float).clip(-20, 20)
        + 0.003 * out["total_net_pnl_bps"].astype(float).clip(-2000, 2000)
        + 0.10 * out["hit_rate"].astype(float)
        - 0.01 * out["max_drawdown_bps"].astype(float).abs().clip(0, 1000)
        + 0.002 * out["trades"].astype(float).clip(0, 300)
    )
    # Prefer candidates with enough calibration trades; use raw rank only as fallback.
    out = out.sort_values(["meets_min_trades", "rank_score", "mean_net_pnl_bps", "total_net_pnl_bps"], ascending=[False, False, False, False]).reset_index(drop=True)
    return out


def run_selective_from_ensemble_dir(
    *,
    ensemble_dir: str | Path,
    out_dir: str | Path,
    horizon_sec: float,
    cost_bps: float = 1.5,
    latency_sec: float = 0.5,
    edge_thresholds: list[float] | None = None,
    min_calibration_trades: int = 8,
    stress_cost_bps_values: list[float] | None = None,
    stress_latency_sec_values: list[float] | None = None,
    signed_columns: list[str] | None = None,
    spread_quantiles: list[float] | None = None,
    vol_modes: list[str] | None = None,
    clean: bool = False,
) -> dict[str, object]:
    """Post-process an ensemble walk-forward run with calibration-only selective filters."""
    source = Path(ensemble_dir)
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    edge_thresholds = edge_thresholds or [0.1, 0.2, 0.3, 0.5, 0.7]
    stress_cost_bps_values = stress_cost_bps_values or [cost_bps, max(3.0, cost_bps * 2.0)]
    stress_latency_sec_values = stress_latency_sec_values or [0.0, latency_sec, max(1.0, latency_sec * 2.0)]

    fold_records: list[dict[str, object]] = []
    all_validation: list[pd.DataFrame] = []
    all_candidate_rows: list[pd.DataFrame] = []
    fold_dirs = sorted(p for p in source.glob("fold_*") if p.is_dir())
    if not fold_dirs:
        raise ValueError(f"no fold directories found in {source}")

    for fold_dir in fold_dirs:
        fold_tag = fold_dir.name.replace("fold_", "")
        fold_num = int(fold_tag) if fold_tag.isdigit() else len(fold_records) + 1
        calib_path = fold_dir / "calibration_predictions.csv"
        valid_path = fold_dir / "validation_predictions.csv"
        if not calib_path.exists() or not valid_path.exists():
            continue
        fold_out = out / f"fold_{fold_num:02d}"
        fold_out.mkdir(parents=True, exist_ok=True)
        calibration = pd.read_csv(calib_path)
        validation = pd.read_csv(valid_path)
        candidates = search_selective_candidates(
            calibration,
            edge_thresholds=edge_thresholds,
            cost_bps=cost_bps,
            horizon_sec=horizon_sec,
            latency_sec=latency_sec,
            min_trades=min_calibration_trades,
            signed_columns=signed_columns,
            spread_quantiles=spread_quantiles,
            vol_modes=vol_modes,
        )
        if candidates.empty:
            raise ValueError(f"no selective candidates generated for {fold_dir}")
        selected_payload = json.loads(str(candidates.iloc[0]["candidate_json"]))
        selected = SelectiveCandidate.from_dict(selected_payload)
        valid_bt, valid_metrics = backtest_selective_taker_bidask_non_overlapping(
            validation,
            candidate=selected,
            cost_bps=cost_bps,
            horizon_sec=horizon_sec,
            latency_sec=latency_sec,
        )
        if "fold" in valid_bt.columns:
            valid_bt["fold"] = fold_num
        else:
            valid_bt.insert(0, "fold", fold_num)
        valid_bt["selected_candidate_json"] = json.dumps(selected.to_dict(), sort_keys=True)
        candidates.insert(0, "fold", fold_num)
        candidates.to_csv(fold_out / "calibration_selective_candidates.csv", index=False)
        valid_bt.to_csv(fold_out / "validation_selective_backtest.csv", index=False)
        (fold_out / "selected_candidate.json").write_text(json.dumps(selected.to_dict(), indent=2), encoding="utf-8")
        all_validation.append(valid_bt)
        all_candidate_rows.append(candidates)
        trades = valid_bt.loc[valid_bt["traded"] == 1, "net_pnl_bps"]
        boot = block_bootstrap_pnl(trades, iterations=500, block_size=10, seed=1000 + fold_num)
        fold_records.append(
            {
                "fold": fold_num,
                "calibration_candidates": int(len(candidates)),
                "selected_candidate_json": json.dumps(selected.to_dict(), sort_keys=True),
                "selected_edge_threshold": selected.edge_threshold,
                "selected_direction_mode": selected.direction_mode,
                "selected_signed_col": selected.signed_col,
                "selected_signed_mode": selected.signed_mode,
                "selected_spread_max_bps": selected.spread_max_bps,
                "selected_vol_mode": selected.vol_mode,
                "valid_trades": float(valid_metrics.get("trades", 0.0)),
                "valid_hit_rate": float(valid_metrics.get("hit_rate", 0.0)),
                "valid_mean_net_pnl_bps": float(valid_metrics.get("mean_net_pnl_bps", 0.0)),
                "valid_total_net_pnl_bps": float(valid_metrics.get("total_net_pnl_bps", 0.0)),
                "valid_max_drawdown_bps": float(valid_metrics.get("max_drawdown_bps", 0.0)),
                "bootstrap_mean_p05_bps": float(boot.get("mean_p05_bps", 0.0)),
                "bootstrap_prob_mean_gt_0": float(boot.get("prob_mean_gt_0", 0.0)),
            }
        )

    folds = pd.DataFrame(fold_records)
    folds.to_csv(out / "fold_metrics.csv", index=False)
    candidates_all = pd.concat(all_candidate_rows, ignore_index=True) if all_candidate_rows else pd.DataFrame()
    candidates_all.to_csv(out / "all_calibration_candidates.csv", index=False)
    oof = pd.concat(all_validation, ignore_index=True) if all_validation else pd.DataFrame()
    oof.to_csv(out / "oof_selective_backtest.csv", index=False)
    stress = stress_fixed_signals(
        oof,
        horizon_sec=horizon_sec,
        cost_bps_values=stress_cost_bps_values,
        latency_sec_values=stress_latency_sec_values,
    ) if not oof.empty else pd.DataFrame()
    stress.to_csv(out / "oof_fixed_signal_stress.csv", index=False)
    gate = fixed_signal_robust_gate(stress, min_trades=max(1, min_calibration_trades)) if not stress.empty else {"passed": False, "reason": "empty stress"}
    actual_frame, actual_metrics_for_null = backtest_fixed_signals_taker_bidask_non_overlapping(
        oof, cost_bps=cost_bps, horizon_sec=horizon_sec, latency_sec=latency_sec
    ) if not oof.empty else (pd.DataFrame(), {})
    shift_null = shift_null_fixed_signals(
        oof, horizon_sec=horizon_sec, cost_bps=cost_bps, latency_sec=latency_sec, shifts=40
    ) if not oof.empty else pd.DataFrame()
    shift_null.to_csv(out / "shift_null_fixed_signals.csv", index=False)
    shift_summary = summarize_shift_null(actual_metrics_for_null, shift_null)
    aggregate = aggregate_selective_folds(folds, oof, stress, gate)
    aggregate.update({f"shift_null_{k}": v for k, v in shift_summary.items()})
    result = {
        "source_ensemble_dir": str(source),
        "horizon_sec": float(horizon_sec),
        "cost_bps": float(cost_bps),
        "latency_sec": float(latency_sec),
        "edge_thresholds": [float(x) for x in edge_thresholds],
        "min_calibration_trades": int(min_calibration_trades),
        "stress_cost_bps_values": [float(x) for x in stress_cost_bps_values],
        "stress_latency_sec_values": [float(x) for x in stress_latency_sec_values],
        "spread_quantiles": [float(x) for x in (spread_quantiles or [1.0, 0.75, 0.5])],
        "vol_modes": list(vol_modes or ["none", "low", "high", "band"]),
        "folds": int(len(folds)),
        "aggregate": aggregate,
        "profit_gate": gate,
        "out_dir": str(out),
    }
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_selective_report(out / "REPORT.md", result, folds, stress)
    return result



def shift_null_fixed_signals(
    predictions_with_signal: pd.DataFrame,
    *,
    horizon_sec: float,
    cost_bps: float,
    latency_sec: float,
    shifts: int = 40,
    min_shift_rows: int | None = None,
) -> pd.DataFrame:
    """Circularly shift raw selected signals relative to the price path.

    This preserves the frequency and clustering of candidate signals while destroying their time alignment with
    subsequent price movement.  A real edge should outperform most shifted-signal null runs.
    """
    if predictions_with_signal.empty:
        return pd.DataFrame()
    base = predictions_with_signal.copy().sort_values("timestamp").reset_index(drop=True)
    raw_col = "raw_selective_signal" if "raw_selective_signal" in base.columns else "signal"
    raw = base[raw_col].fillna(0).astype(int).clip(-1, 1).to_numpy(dtype=int)
    n = len(base)
    if n < 10 or np.count_nonzero(raw) == 0:
        return pd.DataFrame()
    if min_shift_rows is None:
        min_shift_rows = max(1, int(round(float(horizon_sec) / _median_step_sec(base["timestamp"]))))
    min_shift_rows = max(1, min(int(min_shift_rows), n - 1))
    max_shift = max(min_shift_rows, n - min_shift_rows - 1)
    if max_shift <= min_shift_rows:
        shift_values = list(range(1, min(n, shifts + 1)))
    else:
        shift_values = np.linspace(min_shift_rows, max_shift, num=min(int(shifts), max_shift - min_shift_rows + 1), dtype=int).tolist()
    shift_values = sorted(set(int(x) for x in shift_values if 0 < int(x) < n))
    rows: list[dict[str, float]] = []
    for shift in shift_values:
        shifted = np.roll(raw, shift)
        _, metrics = backtest_fixed_signals_taker_bidask_non_overlapping(
            base.assign(signal=shifted),
            cost_bps=cost_bps,
            horizon_sec=horizon_sec,
            latency_sec=latency_sec,
        )
        rows.append({"shift_rows": float(shift), **metrics})
    return pd.DataFrame(rows)


def summarize_shift_null(actual_metrics: dict[str, float], null_frame: pd.DataFrame) -> dict[str, float | int]:
    if null_frame.empty:
        return {"null_runs": 0}
    actual_total = float(actual_metrics.get("total_net_pnl_bps", 0.0))
    actual_mean = float(actual_metrics.get("mean_net_pnl_bps", 0.0))
    total = pd.to_numeric(null_frame["total_net_pnl_bps"], errors="coerce")
    mean = pd.to_numeric(null_frame["mean_net_pnl_bps"], errors="coerce")
    return {
        "null_runs": int(len(null_frame)),
        "actual_total_net_pnl_bps": actual_total,
        "null_total_p50_bps": float(total.quantile(0.50)),
        "null_total_p90_bps": float(total.quantile(0.90)),
        "null_total_p95_bps": float(total.quantile(0.95)),
        "null_total_max_bps": float(total.max()),
        "actual_mean_net_pnl_bps": actual_mean,
        "null_mean_p50_bps": float(mean.quantile(0.50)),
        "null_mean_p90_bps": float(mean.quantile(0.90)),
        "null_mean_p95_bps": float(mean.quantile(0.95)),
        "null_mean_max_bps": float(mean.max()),
        "p_null_total_ge_actual": float((total >= actual_total).mean()),
        "p_null_mean_ge_actual": float((mean >= actual_mean).mean()),
    }


def _median_step_sec(timestamps: pd.Series) -> float:
    ts = timestamps_to_ns(timestamps)
    if len(ts) < 2:
        return 1.0
    diff = np.diff(ts)
    diff = diff[diff > 0]
    if len(diff) == 0:
        return 1.0
    return max(float(np.median(diff) / 1_000_000_000), 1e-9)

def stress_fixed_signals(
    predictions_with_signal: pd.DataFrame,
    *,
    horizon_sec: float,
    cost_bps_values: list[float],
    latency_sec_values: list[float],
) -> pd.DataFrame:
    records: list[dict[str, float]] = []
    for cost in cost_bps_values:
        for latency in latency_sec_values:
            _, metrics = backtest_fixed_signals_taker_bidask_non_overlapping(
                predictions_with_signal,
                cost_bps=float(cost),
                horizon_sec=float(horizon_sec),
                latency_sec=float(latency),
            )
            records.append(metrics)
    out = pd.DataFrame(records)
    if not out.empty:
        out["rank_score"] = (
            out["mean_net_pnl_bps"].astype(float).clip(-20, 20)
            + 0.003 * out["total_net_pnl_bps"].astype(float).clip(-2000, 2000)
            + 0.05 * out["hit_rate"].astype(float)
            - 0.01 * out["max_drawdown_bps"].astype(float).abs().clip(0, 1000)
        )
        out = out.sort_values(["rank_score", "total_net_pnl_bps"], ascending=[False, False]).reset_index(drop=True)
    return out


def fixed_signal_robust_gate(
    stress: pd.DataFrame,
    *,
    min_trades: int = 8,
    min_mean_net_bps: float = 0.0,
    min_total_net_bps: float = 0.0,
) -> dict[str, object]:
    if stress.empty:
        return {"passed": False, "reason": "empty stress"}
    viable = stress[stress["trades"].astype(float) >= float(min_trades)].copy()
    if len(viable) != len(stress):
        return {"passed": False, "reason": "at least one stress cell has too few trades", "viable_cells": int(len(viable)), "cells": int(len(stress))}
    min_mean = float(viable["mean_net_pnl_bps"].min())
    min_total = float(viable["total_net_pnl_bps"].min())
    return {
        "passed": bool(min_mean > min_mean_net_bps and min_total > min_total_net_bps),
        "cells": int(len(stress)),
        "min_trades": float(viable["trades"].min()),
        "min_mean_net_pnl_bps": min_mean,
        "median_mean_net_pnl_bps": float(viable["mean_net_pnl_bps"].median()),
        "min_total_net_pnl_bps": min_total,
        "positive_mean_cells": int((viable["mean_net_pnl_bps"].astype(float) > 0).sum()),
        "positive_total_cells": int((viable["total_net_pnl_bps"].astype(float) > 0).sum()),
    }


def aggregate_selective_folds(folds: pd.DataFrame, oof: pd.DataFrame, stress: pd.DataFrame, gate: dict[str, object]) -> dict[str, object]:
    out: dict[str, object] = {}
    for col in ["valid_trades", "valid_hit_rate", "valid_mean_net_pnl_bps", "valid_total_net_pnl_bps", "bootstrap_mean_p05_bps"]:
        if col in folds.columns:
            vals = pd.to_numeric(folds[col], errors="coerce")
            out[f"{col}_mean"] = float(vals.mean()) if vals.notna().any() else math.nan
            out[f"{col}_min"] = float(vals.min()) if vals.notna().any() else math.nan
    trades = oof[oof.get("traded", pd.Series(dtype=int)).astype(int) == 1] if not oof.empty else pd.DataFrame()
    out["oof_trades"] = int(len(trades))
    out["oof_total_net_pnl_bps"] = float(trades["net_pnl_bps"].sum()) if len(trades) else 0.0
    out["oof_mean_net_pnl_bps"] = float(trades["net_pnl_bps"].mean()) if len(trades) else 0.0
    out["oof_hit_rate"] = float((trades["net_pnl_bps"] > 0).mean()) if len(trades) else 0.0
    out["robust_profit_gate_passed"] = bool(gate.get("passed"))
    out["strict_selective_pass"] = bool(
        out.get("valid_mean_net_pnl_bps_min", -999.0) > 0.0
        and out.get("bootstrap_mean_p05_bps_min", -999.0) > 0.0
        and out.get("oof_mean_net_pnl_bps", -999.0) > 0.0
        and gate.get("passed") is True
    )
    if not stress.empty:
        out["stress_min_mean_net_pnl_bps"] = float(stress["mean_net_pnl_bps"].min())
        out["stress_min_total_net_pnl_bps"] = float(stress["total_net_pnl_bps"].min())
    return out


def write_selective_report(path: str | Path, result: dict[str, object], folds: pd.DataFrame, stress: pd.DataFrame) -> None:
    aggregate = result.get("aggregate", {}) if isinstance(result.get("aggregate"), dict) else {}
    lines = [
        "# V07 Selective Long-window Report",
        "",
        "This report post-processes leak-free ensemble predictions with calibration-only selective filters.",
        "The filters can use current spread, volatility, and signed LOB state, but never future columns.",
        "",
        f"Source ensemble dir: `{result.get('source_ensemble_dir')}`",
        f"Horizon seconds: {result.get('horizon_sec')}",
        f"Cost bps: {result.get('cost_bps')}",
        f"Latency seconds: {result.get('latency_sec')}",
        "",
        "## Fold metrics",
        "",
    ]
    show_cols = [
        "fold",
        "selected_edge_threshold",
        "selected_direction_mode",
        "selected_signed_col",
        "selected_signed_mode",
        "selected_spread_max_bps",
        "selected_vol_mode",
        "valid_trades",
        "valid_hit_rate",
        "valid_mean_net_pnl_bps",
        "valid_total_net_pnl_bps",
        "bootstrap_mean_p05_bps",
    ]
    existing = [c for c in show_cols if c in folds.columns]
    lines.append(folds[existing].to_markdown(index=False) if not folds.empty else "No folds.")
    lines.extend(["", "## Aggregate", "", "```json", json.dumps(aggregate, indent=2), "```", ""])
    lines.extend(["## Shifted-signal null", "", "```json", json.dumps({k: v for k, v in aggregate.items() if str(k).startswith("shift_null_")}, indent=2), "```", ""])
    lines.extend(["## Fixed-signal stress", ""])
    if stress.empty:
        lines.append("No stress rows.")
    else:
        cols = ["cost_bps", "latency_sec", "trades", "hit_rate", "mean_net_pnl_bps", "total_net_pnl_bps", "max_drawdown_bps"]
        lines.append(stress[[c for c in cols if c in stress.columns]].to_markdown(index=False))
    lines.extend(["", "## Profit gate", "", "```json", json.dumps(result.get("profit_gate", {}), indent=2), "```", ""])
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def _candidate_metric_fields(candidate: SelectiveCandidate) -> dict[str, object]:
    return {
        "edge_threshold": float(candidate.edge_threshold),
        "direction_mode": candidate.direction_mode,
        "signed_col": candidate.signed_col,
        "signed_mode": candidate.signed_mode,
        "signed_abs_threshold": float(candidate.signed_abs_threshold or 0.0),
        "spread_max_bps": candidate.spread_max_bps,
        "vol_col": candidate.vol_col,
        "vol_mode": candidate.vol_mode,
        "vol_min": candidate.vol_min,
        "vol_max": candidate.vol_max,
    }


def _assert_no_future_filter(candidate: SelectiveCandidate) -> None:
    for value in [candidate.signed_col, candidate.vol_col]:
        if isinstance(value, str) and value.startswith("future_"):
            raise ValueError("selective filters cannot use future_ columns")


def _dedupe_floats(values: Iterable[float], ndigits: int = 10) -> list[float]:
    out: list[float] = []
    seen: set[float] = set()
    for value in values:
        if not np.isfinite(value):
            continue
        key = round(float(value), ndigits)
        if key not in seen:
            out.append(float(value))
            seen.add(key)
    return out


def _dedupe_optional_floats(values: Iterable[float | None], ndigits: int = 10) -> list[float | None]:
    out: list[float | None] = []
    seen: set[object] = set()
    for value in values:
        key: object = None if value is None else round(float(value), ndigits)
        if key not in seen:
            out.append(None if value is None else float(value))
            seen.add(key)
    return out
