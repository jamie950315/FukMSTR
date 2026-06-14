from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .data_schema import timestamps_to_ns
from .kline_blend import blend_prediction_frames
from .profit_stability import _fast_signal_metrics, _prepare_execution_arrays
from .selective import (
    backtest_fixed_signals_taker_bidask_non_overlapping,
    fixed_signal_robust_gate,
    shift_null_fixed_signals,
    stress_fixed_signals,
    summarize_shift_null,
)
from .stress import block_bootstrap_pnl


def _debug(message: str) -> None:
    if os.environ.get("KLINE_GUARD_DEBUG"):
        print(f"[kline_guard] {message}", flush=True)


@dataclass(frozen=True)
class KlineGuardSpec:
    """Deployable K-line guard applied after the v12 slot-preserving OFI veto.

    The base probability blend first creates a non-overlapping slot schedule.  The OFI veto and this K-line
    guard can only cancel those pre-scheduled slots; cancelled slots still reserve the cooldown window.  This keeps the
    audit conservative and prevents a veto from replacing a rejected trade with a later overlapping winner.

    When `directional` is true the guard value is `slot_signal * kline_col`.  This is useful for signed K-line
    features and for support guards on unsigned risk features: a short slot with unusually large realized-volatility can
    fall outside the calibration support and be vetoed without allowing a replacement slot.
    """

    edge_threshold: float = 0.1
    kline_alpha: float = 0.1
    ofi_col: str = "ofi_sum_l5_norm"
    ofi_quantile: float = 0.9
    kline_col: str = "kline_15s_rv_6_bps"
    kline_quantile: float = 0.0
    kline_operator: str = ">="
    directional: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class KlineGuardGateConfig:
    min_oof_trades: int = 20
    min_periods_with_trades: int = 5
    min_period_mean_net_bps: float = 0.0
    min_bootstrap_p05_bps: float = 0.0
    max_shift_null_p_total: float = 0.10
    max_shift_null_p_mean: float = 0.10
    max_family_null_p_total: float = 0.05
    max_family_null_p_mean: float = 0.10
    require_stress_gate: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_kline_guard_audit(
    *,
    base_ensemble_dir: str | Path,
    kline_ensemble_dir: str | Path,
    out_dir: str | Path,
    horizon_sec: float,
    cost_bps: float = 1.5,
    latency_sec: float = 0.5,
    spec: KlineGuardSpec | None = None,
    stress_cost_bps_values: list[float] | None = None,
    stress_latency_sec_values: list[float] | None = None,
    family_kline_cols: list[str] | None = None,
    family_kline_quantiles: list[float] | None = None,
    shift_null_runs: int = 80,
    family_shift_runs: int = 80,
    gate_config: KlineGuardGateConfig | None = None,
    clean: bool = False,
) -> dict[str, object]:
    base_dir = Path(base_ensemble_dir)
    kline_dir = Path(kline_ensemble_dir)
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    spec = spec or KlineGuardSpec()
    stress_cost_bps_values = stress_cost_bps_values or [1.5, 3.0, 5.0]
    stress_latency_sec_values = stress_latency_sec_values or [0.0, 0.5, 1.0, 2.0]
    family_kline_cols = family_kline_cols or [
        "kline_15s_rv_6_bps",
        "kline_15s_rv_12_bps",
        "kline_1m_rv_3_bps",
        "kline_1m_range_z_6",
        "kline_1s_rv_1_bps",
        "kline_15m_ret_3_bps",
        "kline_15s_signal",
    ]
    family_kline_quantiles = family_kline_quantiles or [0.0, 0.05, 0.10, 0.20, 0.30]
    gate_config = gate_config or KlineGuardGateConfig()

    fold_nums = _fold_numbers(base_dir, kline_dir)
    _debug("fold discovery complete")
    if not fold_nums:
        raise ValueError(f"no matching fold directories found under {base_dir} and {kline_dir}")

    frame_cache: dict[tuple[int, str], pd.DataFrame] = {}
    slot_cache: dict[tuple[int, str], pd.DataFrame] = {}
    for fold in fold_nums:
        for split, name in [("calibration", "calibration_predictions.csv"), ("validation", "validation_predictions.csv")]:
            base_frame = pd.read_csv(base_dir / f"fold_{fold:02d}" / name)
            kline_frame = pd.read_csv(kline_dir / f"fold_{fold:02d}" / name)
            blended = blend_prediction_frames(base_frame, kline_frame, kline_alpha=float(spec.kline_alpha))
            frame_cache[(fold, split)] = blended
            slot_cache[(fold, split)] = _base_slot_frame(
                blended,
                fold=fold,
                edge_threshold=float(spec.edge_threshold),
                horizon_sec=horizon_sec,
                cost_bps=cost_bps,
                latency_sec=latency_sec,
            )

    fold_rows: list[dict[str, object]] = []
    oof_frames: list[pd.DataFrame] = []
    for fold in fold_nums:
        frame, metrics, thresholds = _build_kline_guard_fold(
            calibration=frame_cache[(fold, "calibration")],
            calibration_slots=slot_cache[(fold, "calibration")],
            validation_slots=slot_cache[(fold, "validation")],
            spec=spec,
            fold=fold,
            horizon_sec=horizon_sec,
            cost_bps=cost_bps,
            latency_sec=latency_sec,
        )
        frame.to_csv(out / f"fold_{fold:02d}_kline_guard_backtest.csv", index=False)
        trades = frame.loc[frame["traded"] == 1, "net_pnl_bps"]
        boot = block_bootstrap_pnl(trades, iterations=800, block_size=5, seed=2600 + fold)
        fold_rows.append(
            {
                "fold": fold,
                "ofi_threshold": float(thresholds["ofi_threshold"]),
                "kline_threshold": float(thresholds["kline_threshold"]),
                "events": float(metrics.get("events", 0.0)),
                "trades": int(metrics.get("trades", 0.0)),
                "hit_rate": float(metrics.get("hit_rate", 0.0)),
                "mean_net_pnl_bps": float(metrics.get("mean_net_pnl_bps", 0.0)),
                "total_net_pnl_bps": float(metrics.get("total_net_pnl_bps", 0.0)),
                "max_drawdown_bps": float(metrics.get("max_drawdown_bps", 0.0)),
                "bootstrap_mean_p05_bps": float(boot.get("mean_p05_bps", 0.0)),
                "bootstrap_prob_mean_gt_0": float(boot.get("prob_mean_gt_0", 0.0)),
            }
        )
        oof_frames.append(frame)

    folds = pd.DataFrame(fold_rows)
    folds.to_csv(out / "fold_metrics.csv", index=False)
    _debug("fold metrics written")
    oof = pd.concat(oof_frames, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
    oof.to_csv(out / "kline_guard_oof_backtest.csv", index=False)
    _debug("oof written")

    stress = stress_fixed_signals(
        oof,
        horizon_sec=horizon_sec,
        cost_bps_values=stress_cost_bps_values,
        latency_sec_values=stress_latency_sec_values,
    )
    stress.to_csv(out / "kline_guard_stress.csv", index=False)
    _debug("stress written")
    stress_gate = fixed_signal_robust_gate(stress, min_trades=max(1, gate_config.min_oof_trades))

    actual_frame, actual_metrics = backtest_fixed_signals_taker_bidask_non_overlapping(
        oof,
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
    )
    shift_null = shift_null_fixed_signals(
        oof,
        horizon_sec=horizon_sec,
        cost_bps=cost_bps,
        latency_sec=latency_sec,
        shifts=shift_null_runs,
    )
    shift_null.to_csv(out / "kline_guard_shift_null.csv", index=False)
    _debug("shift null written")
    shift_summary = summarize_shift_null(actual_metrics, shift_null)

    _debug("bootstrap start")
    bootstrap = block_bootstrap_pnl(
        actual_frame.loc[actual_frame["traded"] == 1, "net_pnl_bps"],
        iterations=2000,
        block_size=5,
        seed=2700,
    )

    _debug("family null start")
    family_summary, family_metrics, family_null = _run_kline_guard_family_null(
        fold_nums=fold_nums,
        frame_cache=frame_cache,
        slot_cache=slot_cache,
        selected_spec=spec,
        horizon_sec=horizon_sec,
        cost_bps=cost_bps,
        latency_sec=latency_sec,
        kline_cols=family_kline_cols,
        kline_quantiles=family_kline_quantiles,
        shifts=family_shift_runs,
        min_trades_for_constrained_null=gate_config.min_oof_trades,
    )
    family_metrics.to_csv(out / "kline_guard_family_candidates.csv", index=False)
    _debug("family candidates written")
    family_null.to_csv(out / "kline_guard_family_shift_null.csv", index=False)

    aggregate = _aggregate_kline_guard(
        folds=folds,
        oof=actual_frame,
        bootstrap=bootstrap,
        stress_gate=stress_gate,
        shift_summary=shift_summary,
        family_summary=family_summary,
        gate_config=gate_config,
    )

    result = {
        "base_ensemble_dir": str(base_dir),
        "kline_ensemble_dir": str(kline_dir),
        "horizon_sec": float(horizon_sec),
        "cost_bps": float(cost_bps),
        "latency_sec": float(latency_sec),
        "spec": spec.to_dict(),
        "stress_cost_bps_values": [float(x) for x in stress_cost_bps_values],
        "stress_latency_sec_values": [float(x) for x in stress_latency_sec_values],
        "family_kline_cols": [str(x) for x in family_kline_cols],
        "family_kline_quantiles": [float(x) for x in family_kline_quantiles],
        "shift_null_runs": int(shift_null_runs),
        "family_shift_runs": int(family_shift_runs),
        "folds": int(len(folds)),
        "bootstrap": bootstrap,
        "shift_null": shift_summary,
        "stress_gate": stress_gate,
        "family_null": family_summary,
        "gate_config": gate_config.to_dict(),
        "aggregate": aggregate,
        "out_dir": str(out),
    }
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    _debug("summary written")
    _write_report(out / "REPORT.md", result, folds, stress, family_metrics)
    _debug("report written")
    return result


def _fold_numbers(base_dir: Path, kline_dir: Path) -> list[int]:
    nums: list[int] = []
    for p in sorted(base_dir.glob("fold_*")):
        if not p.is_dir():
            continue
        tag = p.name.replace("fold_", "")
        if not tag.isdigit():
            continue
        fold = int(tag)
        if (kline_dir / f"fold_{fold:02d}").is_dir():
            nums.append(fold)
    return nums


def _base_slot_frame(
    frame: pd.DataFrame,
    *,
    fold: int,
    edge_threshold: float,
    horizon_sec: float,
    cost_bps: float,
    latency_sec: float,
) -> pd.DataFrame:
    edge = frame["prob_up"].astype(float) - frame["prob_down"].astype(float)
    raw_signal = np.where(edge >= edge_threshold, 1, np.where(edge <= -edge_threshold, -1, 0)).astype(int)
    slots, _ = backtest_fixed_signals_taker_bidask_non_overlapping(
        frame.assign(signal=raw_signal, fold=fold),
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
    )
    slots["fold"] = int(fold)
    return slots


def _build_kline_guard_fold(
    *,
    calibration: pd.DataFrame,
    calibration_slots: pd.DataFrame,
    validation_slots: pd.DataFrame,
    spec: KlineGuardSpec,
    fold: int,
    horizon_sec: float,
    cost_bps: float,
    latency_sec: float,
) -> tuple[pd.DataFrame, dict[str, float], dict[str, float]]:
    if spec.ofi_col not in calibration.columns or spec.ofi_col not in validation_slots.columns:
        raise ValueError(f"OFI column missing: {spec.ofi_col}")
    if spec.kline_col not in calibration_slots.columns or spec.kline_col not in validation_slots.columns:
        raise ValueError(f"K-line column missing: {spec.kline_col}")
    ofi_threshold = float(pd.to_numeric(calibration[spec.ofi_col], errors="coerce").quantile(float(spec.ofi_quantile)))
    calib_slot_mask = (calibration_slots["traded"].astype(int) == 1) & (
        pd.to_numeric(calibration_slots[spec.ofi_col], errors="coerce") <= ofi_threshold
    )
    calib_guard_values = _guard_values(calibration_slots.loc[calib_slot_mask], spec)
    calib_guard_values = calib_guard_values[np.isfinite(calib_guard_values)]
    kline_threshold = float(np.quantile(calib_guard_values, float(spec.kline_quantile))) if len(calib_guard_values) else 0.0

    base_traded = validation_slots["traded"].astype(int) == 1
    ofi_keep = pd.to_numeric(validation_slots[spec.ofi_col], errors="coerce") <= ofi_threshold
    guard_values = _guard_values(validation_slots, spec)
    if spec.kline_operator == ">=":
        kline_keep = guard_values >= kline_threshold
    elif spec.kline_operator == "<=":
        kline_keep = guard_values <= kline_threshold
    else:
        raise ValueError("kline_operator must be '>=' or '<='")
    slot_mask = base_traded.to_numpy() & ofi_keep.fillna(False).to_numpy() & kline_keep
    selected_signal = np.zeros(len(validation_slots), dtype=int)
    selected_signal[slot_mask] = validation_slots.loc[slot_mask, "signal"].astype(int).to_numpy()
    frame, metrics = backtest_fixed_signals_taker_bidask_non_overlapping(
        validation_slots.assign(signal=selected_signal, fold=fold),
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
    )
    frame["fold"] = int(fold)
    frame["base_slot_signal"] = validation_slots["signal"].astype(int).to_numpy()
    frame["base_slot_traded"] = validation_slots["traded"].astype(int).to_numpy()
    frame["ofi_veto_passed"] = (base_traded.to_numpy() & ofi_keep.fillna(False).to_numpy()).astype(int)
    frame["kline_veto_passed"] = slot_mask.astype(int)
    frame["ofi_filter_col"] = spec.ofi_col
    frame["ofi_filter_quantile"] = float(spec.ofi_quantile)
    frame["ofi_filter_threshold"] = float(ofi_threshold)
    frame["kline_filter_col"] = spec.kline_col
    frame["kline_filter_quantile"] = float(spec.kline_quantile)
    frame["kline_filter_threshold"] = float(kline_threshold)
    frame["kline_guard_directional"] = int(bool(spec.directional))
    frame["kline_guard_value"] = guard_values.astype(float)
    frame = _slim_audit_frame(frame)
    return frame, metrics, {"ofi_threshold": ofi_threshold, "kline_threshold": kline_threshold}


def _guard_values(frame: pd.DataFrame, spec: KlineGuardSpec) -> np.ndarray:
    values = pd.to_numeric(frame[spec.kline_col], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    if spec.directional:
        sig = frame.get("signal", pd.Series(0, index=frame.index)).fillna(0).astype(int).clip(-1, 1).to_numpy(dtype=int)
        values = sig * values
    return values



def _slim_backtest_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep only columns needed for shifted/family null re-pricing.

    Candidate family audits can create many OOF ledgers.  The blended K-line prediction frames carry hundreds of
    feature columns, but the fixed-signal re-pricer only needs timestamps, bid/ask, signal, and a few audit columns.
    Slimming avoids large temporary DataFrames while preserving all metrics exactly.
    """
    preferred = ["fold", "timestamp", "best_bid", "best_ask", "signal"]
    keep = [c for c in preferred if c in frame.columns]
    return frame.loc[:, keep].copy()


def _slim_audit_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep the deployable fixed-signal ledger plus veto audit columns, dropping hundreds of raw K-line features."""
    preferred = [
        "fold",
        "timestamp",
        "best_bid",
        "best_ask",
        "signal",
        "raw_selective_signal",
        "traded",
        "entry_px_taker",
        "exit_px_taker",
        "latency_sec",
        "gross_pnl_bps",
        "cost_bps",
        "net_pnl_bps",
        "equity_bps",
        "base_slot_signal",
        "base_slot_traded",
        "ofi_veto_passed",
        "kline_veto_passed",
        "ofi_filter_col",
        "ofi_filter_quantile",
        "ofi_filter_threshold",
        "kline_filter_col",
        "kline_filter_quantile",
        "kline_filter_threshold",
        "kline_guard_directional",
        "kline_guard_value",
    ]
    keep = [c for c in preferred if c in frame.columns]
    return frame.loc[:, keep].copy()


def _fast_fixed_signal_metrics(
    frame: pd.DataFrame,
    raw_signal: np.ndarray,
    *,
    cost_bps: float,
    horizon_sec: float,
    latency_sec: float,
) -> dict[str, float]:
    """Metric-only fixed-signal taker/bid-ask re-pricer used by family null loops.

    It mirrors backtest_fixed_signals_taker_bidask_non_overlapping but avoids constructing a full DataFrame for every
    shifted null candidate.
    """
    n = len(frame)
    if n == 0:
        return {
            "events": 0.0,
            "trades": 0.0,
            "trade_rate": 0.0,
            "hit_rate": 0.0,
            "mean_net_pnl_bps": 0.0,
            "median_net_pnl_bps": 0.0,
            "total_net_pnl_bps": 0.0,
            "sharpe_like": 0.0,
            "max_drawdown_bps": 0.0,
            "profit_factor": 0.0,
        }
    raw = np.asarray(raw_signal, dtype=int)[:n]
    if len(raw) < n:
        raw = np.pad(raw, (0, n - len(raw)))
    raw = np.clip(raw, -1, 1)
    ts_ns = timestamps_to_ns(frame["timestamp"])
    bid = frame["best_bid"].astype(float).to_numpy()
    ask = frame["best_ask"].astype(float).to_numpy()
    horizon_ns = int(float(horizon_sec) * 1_000_000_000)
    latency_ns = int(float(latency_sec) * 1_000_000_000)
    entry_target = ts_ns + latency_ns
    exit_target = ts_ns + horizon_ns
    entry_idx = np.searchsorted(ts_ns, entry_target, side="left")
    exit_idx = np.searchsorted(ts_ns, exit_target, side="left")
    valid = (entry_idx < n) & (exit_idx < n) & (entry_target < exit_target)
    next_allowed = -np.inf
    pnl_values: list[float] = []
    for i, (sig, ts) in enumerate(zip(raw, ts_ns)):
        if sig == 0 or ts < next_allowed or not valid[i]:
            continue
        ei = int(entry_idx[i])
        xi = int(exit_idx[i])
        if sig > 0:
            ep = ask[ei]
            xp = bid[xi]
            gross = (xp - ep) / ep * 10000.0
        else:
            ep = bid[ei]
            xp = ask[xi]
            gross = (ep - xp) / ep * 10000.0
        if not (np.isfinite(ep) and np.isfinite(xp) and ep > 0 and xp > 0):
            continue
        pnl_values.append(float(gross - float(cost_bps)))
        next_allowed = int(ts) + horizon_ns
    trades = len(pnl_values)
    base = {"events": float(n), "trades": float(trades), "trade_rate": float(trades / n) if n else 0.0}
    if trades == 0:
        return {
            **base,
            "hit_rate": 0.0,
            "mean_net_pnl_bps": 0.0,
            "median_net_pnl_bps": 0.0,
            "total_net_pnl_bps": 0.0,
            "sharpe_like": 0.0,
            "max_drawdown_bps": 0.0,
            "profit_factor": 0.0,
        }
    pnl = np.asarray(pnl_values, dtype=float)
    std = float(pnl.std(ddof=1)) if trades > 1 else 0.0
    equity = np.cumsum(pnl)
    drawdown = equity - np.maximum.accumulate(equity)
    gross_profit = float(pnl[pnl > 0].sum())
    gross_loss = float(-pnl[pnl < 0].sum())
    return {
        **base,
        "hit_rate": float((pnl > 0).mean()),
        "mean_net_pnl_bps": float(pnl.mean()),
        "median_net_pnl_bps": float(np.median(pnl)),
        "total_net_pnl_bps": float(pnl.sum()),
        "sharpe_like": float(pnl.mean() / std * np.sqrt(trades)) if std > 0 else 0.0,
        "max_drawdown_bps": float(drawdown.min()) if len(drawdown) else 0.0,
        "profit_factor": float(gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0),
    }

def _run_kline_guard_family_null(
    *,
    fold_nums: list[int],
    frame_cache: dict[tuple[int, str], pd.DataFrame],
    slot_cache: dict[tuple[int, str], pd.DataFrame],
    selected_spec: KlineGuardSpec,
    horizon_sec: float,
    cost_bps: float,
    latency_sec: float,
    kline_cols: list[str],
    kline_quantiles: list[float],
    shifts: int,
    min_trades_for_constrained_null: int,
) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame]:
    candidates: list[dict[str, object]] = []
    _debug(f"family grid cols={len(kline_cols)} quantiles={kline_quantiles} shifts={shifts}")
    for col in kline_cols:
        for q in kline_quantiles:
            _debug(f"family candidate start {col} q={q}")
            spec = KlineGuardSpec(
                edge_threshold=selected_spec.edge_threshold,
                kline_alpha=selected_spec.kline_alpha,
                ofi_col=selected_spec.ofi_col,
                ofi_quantile=selected_spec.ofi_quantile,
                kline_col=col,
                kline_quantile=float(q),
                kline_operator=selected_spec.kline_operator,
                directional=selected_spec.directional,
            )
            frames: list[pd.DataFrame] = []
            for fold in fold_nums:
                frame, _, _ = _build_kline_guard_fold(
                    calibration=frame_cache[(fold, "calibration")],
                    calibration_slots=slot_cache[(fold, "calibration")],
                    validation_slots=slot_cache[(fold, "validation")],
                    spec=spec,
                    fold=fold,
                    horizon_sec=horizon_sec,
                    cost_bps=cost_bps,
                    latency_sec=latency_sec,
                )
                frames.append(_slim_backtest_frame(frame))
            oof = pd.concat(frames, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
            raw = oof["signal"].fillna(0).astype(int).clip(-1, 1).to_numpy(dtype=int)
            arrays = _prepare_execution_arrays(oof, horizon_sec=horizon_sec, latency_sec=latency_sec)
            metrics, _ = _fast_signal_metrics(raw, arrays, cost_bps=cost_bps)
            candidates.append({"spec": spec, "oof": oof, "raw": raw, "arrays": arrays, "metrics": metrics})
            _debug(f"family candidate done {col} q={q} trades={metrics.get('trades', 0)} total={metrics.get('total_net_pnl_bps', 0)}")

    metric_rows: list[dict[str, object]] = []
    for item in candidates:
        spec = item["spec"]
        metric_rows.append({**spec.to_dict(), **item["metrics"]})
    metrics_df = pd.DataFrame(metric_rows).sort_values(["total_net_pnl_bps", "mean_net_pnl_bps"], ascending=[False, False]).reset_index(drop=True)

    selected_key = selected_spec.to_dict()
    selected_item = next(item for item in candidates if item["spec"].to_dict() == selected_key)
    selected_metrics = selected_item["metrics"]
    n = len(selected_item["raw"])
    shift_values = _shift_values(n=n, shifts=shifts, min_shift=max(1, int(round(float(horizon_sec) / 0.5))))
    null_rows: list[dict[str, object]] = []
    for idx, shift in enumerate(shift_values):
        if idx % 10 == 0:
            _debug(f"family shift {idx + 1}/{len(shift_values)}")
        max_total = -1e18
        max_mean = -1e18
        max_total_constrained = -1e18
        max_mean_constrained = -1e18
        best_total_spec = ""
        for item in candidates:
            raw = np.roll(item["raw"], int(shift) % len(item["raw"]))
            metrics, _ = _fast_signal_metrics(raw, item["arrays"], cost_bps=cost_bps)
            total = float(metrics.get("total_net_pnl_bps", 0.0))
            mean = float(metrics.get("mean_net_pnl_bps", 0.0))
            trades = float(metrics.get("trades", 0.0))
            if total > max_total:
                max_total = total
                best_total_spec = json.dumps(item["spec"].to_dict(), sort_keys=True)
            max_mean = max(max_mean, mean)
            if trades >= float(min_trades_for_constrained_null):
                max_total_constrained = max(max_total_constrained, total)
                max_mean_constrained = max(max_mean_constrained, mean)
        null_rows.append(
            {
                "shift_rows": int(shift),
                "max_total_net_pnl_bps": float(max_total),
                "max_mean_net_pnl_bps": float(max_mean),
                "max_total_net_pnl_bps_constrained": float(max_total_constrained),
                "max_mean_net_pnl_bps_constrained": float(max_mean_constrained),
                "best_total_spec_json": best_total_spec,
            }
        )
    null_df = pd.DataFrame(null_rows)
    total = pd.to_numeric(null_df["max_total_net_pnl_bps"], errors="coerce")
    mean = pd.to_numeric(null_df["max_mean_net_pnl_bps"], errors="coerce")
    total_c = pd.to_numeric(null_df["max_total_net_pnl_bps_constrained"], errors="coerce")
    mean_c = pd.to_numeric(null_df["max_mean_net_pnl_bps_constrained"], errors="coerce")
    selected_total = float(selected_metrics.get("total_net_pnl_bps", 0.0))
    selected_mean = float(selected_metrics.get("mean_net_pnl_bps", 0.0))
    summary = {
        "candidate_count": int(len(candidates)),
        "selected_total_net_pnl_bps": selected_total,
        "selected_mean_net_pnl_bps": selected_mean,
        "selected_trades": float(selected_metrics.get("trades", 0.0)),
        "family_null_runs": int(len(null_df)),
        "p_family_max_total_ge_selected": float((total >= selected_total).mean()) if len(total) else 1.0,
        "p_family_max_mean_ge_selected": float((mean >= selected_mean).mean()) if len(mean) else 1.0,
        "p_family_constrained_max_total_ge_selected": float((total_c >= selected_total).mean()) if len(total_c) else 1.0,
        "p_family_constrained_max_mean_ge_selected": float((mean_c >= selected_mean).mean()) if len(mean_c) else 1.0,
        "family_null_total_p95_bps": float(total.quantile(0.95)) if len(total) else 0.0,
        "family_null_mean_p95_bps": float(mean.quantile(0.95)) if len(mean) else 0.0,
        "family_constrained_null_total_p95_bps": float(total_c.quantile(0.95)) if len(total_c) else 0.0,
        "family_constrained_null_mean_p95_bps": float(mean_c.quantile(0.95)) if len(mean_c) else 0.0,
    }
    return summary, metrics_df, null_df


def _shift_values(*, n: int, shifts: int, min_shift: int) -> list[int]:
    if n <= 2:
        return []
    min_shift = max(1, min(int(min_shift), n - 1))
    max_shift = max(min_shift, n - min_shift - 1)
    if max_shift <= min_shift:
        values = list(range(1, min(n, shifts + 1)))
    else:
        values = np.linspace(min_shift, max_shift, num=min(int(shifts), max_shift - min_shift + 1), dtype=int).tolist()
    return sorted(set(int(x) for x in values if 0 < int(x) < n))


def _aggregate_kline_guard(
    *,
    folds: pd.DataFrame,
    oof: pd.DataFrame,
    bootstrap: dict[str, float],
    stress_gate: dict[str, object],
    shift_summary: dict[str, object],
    family_summary: dict[str, object],
    gate_config: KlineGuardGateConfig,
) -> dict[str, object]:
    trades = oof[oof["traded"] == 1].copy()
    periods_with_trades = int((folds["trades"].astype(float) > 0).sum()) if not folds.empty else 0
    summary = {
        "trades": int(len(trades)),
        "hit_rate": float((trades["net_pnl_bps"] > 0).mean()) if len(trades) else 0.0,
        "mean_net_pnl_bps": float(trades["net_pnl_bps"].mean()) if len(trades) else 0.0,
        "total_net_pnl_bps": float(trades["net_pnl_bps"].sum()) if len(trades) else 0.0,
        "periods_with_trades": periods_with_trades,
        "period_trades_min": int(folds["trades"].min()) if not folds.empty else 0,
        "period_mean_net_pnl_bps_min": float(folds["mean_net_pnl_bps"].min()) if not folds.empty else 0.0,
        "period_total_net_pnl_bps_min": float(folds["total_net_pnl_bps"].min()) if not folds.empty else 0.0,
        "bootstrap_mean_p05_bps": float(bootstrap.get("mean_p05_bps", 0.0)),
        "bootstrap_total_p05_bps": float(bootstrap.get("total_p05_bps", 0.0)),
        "stress_gate_passed": bool(stress_gate.get("passed")),
        "shift_null_p_total": float(shift_summary.get("p_null_total_ge_actual", 1.0)),
        "shift_null_p_mean": float(shift_summary.get("p_null_mean_ge_actual", 1.0)),
        "family_null_p_total": float(family_summary.get("p_family_max_total_ge_selected", 1.0)),
        "family_null_p_mean": float(family_summary.get("p_family_max_mean_ge_selected", 1.0)),
        "family_constrained_null_p_total": float(family_summary.get("p_family_constrained_max_total_ge_selected", 1.0)),
        "family_constrained_null_p_mean": float(family_summary.get("p_family_constrained_max_mean_ge_selected", 1.0)),
    }
    checks = {
        "enough_oof_trades": summary["trades"] >= gate_config.min_oof_trades,
        "enough_periods_with_trades": summary["periods_with_trades"] >= gate_config.min_periods_with_trades,
        "positive_period_min_mean": summary["period_mean_net_pnl_bps_min"] > gate_config.min_period_mean_net_bps,
        "positive_bootstrap_p05": summary["bootstrap_mean_p05_bps"] > gate_config.min_bootstrap_p05_bps,
        "stress_gate_ok": (not gate_config.require_stress_gate) or summary["stress_gate_passed"],
        "shift_null_total_ok": summary["shift_null_p_total"] <= gate_config.max_shift_null_p_total,
        "shift_null_mean_ok": summary["shift_null_p_mean"] <= gate_config.max_shift_null_p_mean,
        "family_null_total_ok": summary["family_null_p_total"] <= gate_config.max_family_null_p_total,
        "family_null_mean_ok": summary["family_null_p_mean"] <= gate_config.max_family_null_p_mean,
        "family_constrained_null_total_ok": summary["family_constrained_null_p_total"] <= gate_config.max_family_null_p_total,
        "family_constrained_null_mean_ok": summary["family_constrained_null_p_mean"] <= gate_config.max_family_null_p_mean,
    }
    summary["gate"] = {
        "passed": bool(all(checks.values())),
        "checks": checks,
        "failed_checks": [k for k, v in checks.items() if not v],
    }
    return summary


def _write_report(path: str | Path, result: dict[str, object], folds: pd.DataFrame, stress: pd.DataFrame, family_metrics: pd.DataFrame) -> None:
    agg = result.get("aggregate", {}) if isinstance(result.get("aggregate"), dict) else {}
    gate = agg.get("gate", {}) if isinstance(agg.get("gate"), dict) else {}
    fam = result.get("family_null", {}) if isinstance(result.get("family_null"), dict) else {}
    stress_gate = result.get("stress_gate", {}) if isinstance(result.get("stress_gate"), dict) else {}
    spec = result.get("spec", {})
    lines = [
        "# V14 K-line Guard Audit Report",
        "",
        f"Base ensemble: `{result.get('base_ensemble_dir')}`",
        f"K-line ensemble: `{result.get('kline_ensemble_dir')}`",
        f"Horizon: `{result.get('horizon_sec')}` seconds",
        f"Cost / latency: `{result.get('cost_bps')}` bps / `{result.get('latency_sec')}` seconds",
        f"Spec: `{json.dumps(spec, sort_keys=True)}`",
        "",
        "## Aggregate",
        "",
        f"Gate passed: `{gate.get('passed')}`",
        f"Trades: `{agg.get('trades')}`",
        f"Hit rate: `{agg.get('hit_rate')}`",
        f"Mean net PnL bps: `{agg.get('mean_net_pnl_bps')}`",
        f"Total net PnL bps: `{agg.get('total_net_pnl_bps')}`",
        f"Worst fold mean bps: `{agg.get('period_mean_net_pnl_bps_min')}`",
        f"Bootstrap mean p05 bps: `{agg.get('bootstrap_mean_p05_bps')}`",
        f"Stress min mean bps: `{stress_gate.get('min_mean_net_pnl_bps')}`",
        f"Stress min total bps: `{stress_gate.get('min_total_net_pnl_bps')}`",
        f"Shift-null p(total): `{agg.get('shift_null_p_total')}`",
        f"Shift-null p(mean): `{agg.get('shift_null_p_mean')}`",
        f"K-line-family p(total): `{fam.get('p_family_max_total_ge_selected')}`",
        f"K-line-family p(mean): `{fam.get('p_family_max_mean_ge_selected')}`",
        "",
        "## Fold metrics",
        "",
        folds.to_markdown(index=False) if not folds.empty else "No fold metrics.",
        "",
        "## Stress",
        "",
        stress.to_markdown(index=False) if not stress.empty else "No stress metrics.",
        "",
        "## Top family candidates",
        "",
        family_metrics.head(20).to_markdown(index=False) if not family_metrics.empty else "No family candidates.",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
