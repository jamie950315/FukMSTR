from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .exit_lock import ExitLockSpec, backtest_fixed_signals_taker_bidask_exit_lock, execution_path_arrays, fast_exit_lock_metrics
from .kline_guard import KlineGuardSpec
from .profit_lock import _jsonable, _path_diagnostics
from .profit_stability import _prepare_execution_arrays
from .profit_success_fast import _candidate, _dedupe, _family_specs, _key, _load_alpha_data, _stability
from .slot_veto import _shift_values
from .stress import block_bootstrap_pnl


@dataclass(frozen=True)
class ExecutionProfitLockGate:
    """V17 execution-lock certificate gate.

    This gate keeps the V15/V16 entry signal frozen and evaluates only a slot-preserving
    take-profit exit lock.  The full severe stress grid is part of the pass condition.
    """

    min_oof_trades: int = 20
    min_folds_with_trades: int = 5
    min_fold_mean_net_bps: float = 0.0
    min_fold_total_net_bps: float = 0.0
    min_bootstrap_mean_p05_bps: float = 0.0
    max_addone_family_p: float = 0.01
    min_top_winner_removal_k: int = 5
    min_top_winner_removed_total_bps: float = 0.0
    min_full_stress_mean_net_bps: float = 0.0
    min_full_stress_total_net_bps: float = 0.0
    min_equal_trade_blocks_5_positive: int = 5
    min_equal_trade_blocks_10_positive: int = 10

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_execution_profit_lock_certificate(
    *,
    base_ensemble_dir: str | Path,
    kline_ensemble_dir: str | Path,
    out_dir: str | Path,
    horizon_sec: float = 90.0,
    cost_bps: float = 1.5,
    latency_sec: float = 0.5,
    selected_signal_spec: KlineGuardSpec | None = None,
    selected_exit_spec: ExitLockSpec | None = None,
    alpha_grid: list[float] | None = None,
    ofi_cols: list[str] | None = None,
    ofi_quantiles: list[float] | None = None,
    kline_cols: list[str] | None = None,
    kline_quantiles: list[float] | None = None,
    exit_take_profit_bps_values: list[float] | None = None,
    exit_stop_loss_bps_values: list[float] | None = None,
    stress_cost_bps_values: list[float] | None = None,
    stress_latency_sec_values: list[float] | None = None,
    shift_null_runs: int = 1000,
    gate: ExecutionProfitLockGate | None = None,
    clean: bool = False,
) -> dict[str, object]:
    base = Path(base_ensemble_dir)
    kline = Path(kline_ensemble_dir)
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    selected_signal_spec = selected_signal_spec or KlineGuardSpec(
        edge_threshold=0.1,
        kline_alpha=0.125,
        ofi_col="ofi_sum_l5_norm",
        ofi_quantile=0.9,
        kline_col="kline_15s_rv_6_bps",
        kline_quantile=0.0,
        kline_operator=">=",
        directional=True,
    )
    selected_exit_spec = selected_exit_spec or ExitLockSpec(take_profit_bps=40.0, stop_loss_bps=0.0, reserve_horizon=True)
    alpha_grid = _dedupe(alpha_grid or [0.0, 0.025, 0.05, 0.075, 0.1, 0.125, 0.15, selected_signal_spec.kline_alpha])
    ofi_cols = ofi_cols or ["ofi_sum_l3_norm", "ofi_sum_l5_norm", "ofi_sum_l10_norm"]
    ofi_quantiles = _dedupe(ofi_quantiles or [0.5, 0.6, 0.7, 0.8, 0.9])
    kline_cols = kline_cols or [
        "kline_15s_rv_6_bps",
        "kline_15s_rv_12_bps",
        "kline_1m_rv_3_bps",
        "kline_1m_range_z_6",
        "kline_1s_rv_1_bps",
        "kline_15m_ret_3_bps",
        "kline_15s_signal",
    ]
    kline_quantiles = _dedupe(kline_quantiles or [0.0])
    exit_take_profit_bps_values = _dedupe(exit_take_profit_bps_values or [0.0, 20.0, 30.0, 40.0, 60.0, 90.0, selected_exit_spec.take_profit_bps])
    exit_stop_loss_bps_values = _dedupe(exit_stop_loss_bps_values or [0.0, selected_exit_spec.stop_loss_bps])
    stress_cost_bps_values = _dedupe(stress_cost_bps_values or [1.5, 3.0, 5.0, 7.5, 10.0])
    stress_latency_sec_values = _dedupe(stress_latency_sec_values or [0.0, 0.5, 1.0, 2.0, 3.0, 5.0])
    gate = gate or ExecutionProfitLockGate()

    signal_specs = _family_specs(selected_signal_spec, alpha_grid, ofi_cols, ofi_quantiles, kline_cols, kline_quantiles)
    required = sorted({selected_signal_spec.ofi_col, selected_signal_spec.kline_col, *ofi_cols, *kline_cols})
    alphas = sorted({float(alpha) for alpha, _, _ in signal_specs})
    data = _load_alpha_data(base, kline, alphas, required, selected_signal_spec.edge_threshold, horizon_sec, cost_bps, latency_sec)
    canonical = data[float(selected_signal_spec.kline_alpha)]["oof"].copy().sort_values("timestamp").reset_index(drop=True)
    arrays = execution_path_arrays(canonical, horizon_sec=horizon_sec, latency_sec=latency_sec)
    fixed_arrays = _prepare_execution_arrays(canonical, horizon_sec=horizon_sec, latency_sec=latency_sec)

    signal_candidates: list[dict[str, object]] = []
    selected_signal: dict[str, object] | None = None
    for alpha, spec, tags in signal_specs:
        cand = _candidate(float(alpha), spec, tags, data[float(alpha)], fixed_arrays, cost_bps, horizon_sec, latency_sec)
        signal_candidates.append(cand)
        if _key(float(alpha), spec) == _key(float(selected_signal_spec.kline_alpha), selected_signal_spec):
            selected_signal = cand
    if selected_signal is None:
        raise RuntimeError("selected frozen signal was not generated")

    exit_specs = _dedupe_exit_specs(
        [
            ExitLockSpec(take_profit_bps=tp, stop_loss_bps=sl, reserve_horizon=True)
            for tp in exit_take_profit_bps_values
            for sl in exit_stop_loss_bps_values
        ]
    )

    combos: list[dict[str, object]] = []
    selected_combo: dict[str, object] | None = None
    for sig_cand in signal_candidates:
        for exit_spec in exit_specs:
            metrics, pnl, reasons, holds = fast_exit_lock_metrics(sig_cand["raw"], arrays, cost_bps=cost_bps, spec=exit_spec)
            tags = set(sig_cand["tags"])
            tags.add("selected_exit" if _same_exit(exit_spec, selected_exit_spec) else "exit_family")
            combo = {
                "signal": sig_cand,
                "exit": exit_spec,
                "raw": np.asarray(sig_cand["raw"], dtype=int),
                "tags": tuple(sorted(tags)),
                "metrics": metrics,
            }
            combos.append(combo)
            if _key(sig_cand["alpha"], sig_cand["spec"]) == _key(float(selected_signal_spec.kline_alpha), selected_signal_spec) and _same_exit(exit_spec, selected_exit_spec):
                selected_combo = combo
    if selected_combo is None:
        raise RuntimeError("selected execution-lock combo was not generated")

    selected_oof = canonical.copy()
    selected_oof["signal"] = np.asarray(selected_combo["raw"], dtype=int)
    selected_bt, selected_metrics = backtest_fixed_signals_taker_bidask_exit_lock(
        selected_oof,
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
        spec=selected_exit_spec,
    )
    selected_bt["fold"] = canonical["fold"].to_numpy()
    selected_bt.to_csv(out / "execution_lock_oof_backtest.csv", index=False)

    folds = _fold_metrics(canonical, np.asarray(selected_combo["raw"], dtype=int), selected_exit_spec, cost_bps, horizon_sec, latency_sec)
    folds.to_csv(out / "fold_metrics.csv", index=False)
    candidates = _candidate_frame(combos)
    candidates.to_csv(out / "execution_lock_family_candidates.csv", index=False)

    trades = selected_bt.loc[selected_bt["traded"].astype(int) == 1].reset_index(drop=True)
    pnl = pd.to_numeric(trades["net_pnl_bps"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    bootstrap = block_bootstrap_pnl(pnl, iterations=5000, block_size=5, seed=57017)
    stability = _stability(selected_bt)
    path = _path_diagnostics(pnl, trades["fold"].to_numpy(dtype=int) if "fold" in trades.columns else np.asarray([], dtype=int))

    stress = _stress_exit_lock(canonical, np.asarray(selected_combo["raw"], dtype=int), selected_exit_spec, horizon_sec, cost_bps_values=stress_cost_bps_values, latency_sec_values=stress_latency_sec_values)
    stress.to_csv(out / "execution_lock_severe_stress.csv", index=False)
    stress_summary = _stress_summary(stress)

    null_df, family_null = _sparse_exit_family_shift_null(
        selected=selected_combo,
        combos=combos,
        arrays=arrays,
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        shift_null_runs=shift_null_runs,
        min_trades=gate.min_oof_trades,
    )
    null_df.to_csv(out / "execution_lock_sparse_family_shift_null.csv", index=False)

    aggregate = _aggregate(
        selected_metrics=selected_metrics,
        folds=folds,
        bootstrap=bootstrap,
        stability=stability,
        path=path,
        stress_summary=stress_summary,
        family_null=family_null,
        gate=gate,
    )
    result: dict[str, object] = {
        "base_ensemble_dir": str(base),
        "kline_ensemble_dir": str(kline),
        "horizon_sec": float(horizon_sec),
        "cost_bps": float(cost_bps),
        "latency_sec": float(latency_sec),
        "selected_signal_spec": selected_signal_spec.to_dict(),
        "selected_exit_spec": selected_exit_spec.to_dict(),
        "alpha_grid": [float(x) for x in alpha_grid],
        "ofi_cols": [str(x) for x in ofi_cols],
        "ofi_quantiles": [float(x) for x in ofi_quantiles],
        "kline_cols": [str(x) for x in kline_cols],
        "kline_quantiles": [float(x) for x in kline_quantiles],
        "exit_take_profit_bps_values": [float(x) for x in exit_take_profit_bps_values],
        "exit_stop_loss_bps_values": [float(x) for x in exit_stop_loss_bps_values],
        "stress_cost_bps_values": [float(x) for x in stress_cost_bps_values],
        "stress_latency_sec_values": [float(x) for x in stress_latency_sec_values],
        "shift_null_runs": int(len(null_df)),
        "selected_metrics": _jsonable(selected_metrics),
        "bootstrap": _jsonable(bootstrap),
        "stability": _jsonable(stability),
        "path_diagnostics": _jsonable(path),
        "stress_summary": _jsonable(stress_summary),
        "family_null": _jsonable(family_null),
        "aggregate": _jsonable(aggregate),
        "gate_config": gate.to_dict(),
        "out_dir": str(out),
    }
    (out / "summary.json").write_text(json.dumps(_jsonable(result), indent=2), encoding="utf-8")
    _write_report(out / "REPORT.md", result, folds, candidates, stress)
    (out / "DONE.marker").write_text("ok\n", encoding="utf-8")
    return result


def _fold_metrics(canonical: pd.DataFrame, raw: np.ndarray, spec: ExitLockSpec, cost_bps: float, horizon_sec: float, latency_sec: float) -> pd.DataFrame:
    frame = canonical.copy()
    frame["signal"] = np.asarray(raw, dtype=int)
    rows: list[dict[str, object]] = []
    for fold in sorted(frame["fold"].unique()):
        sub = frame.loc[frame["fold"] == fold].copy()
        _, metrics = backtest_fixed_signals_taker_bidask_exit_lock(sub, cost_bps=cost_bps, horizon_sec=horizon_sec, latency_sec=latency_sec, spec=spec)
        rows.append({"fold": int(fold), **_jsonable(metrics)})
    return pd.DataFrame(rows)


def _stress_exit_lock(canonical: pd.DataFrame, raw: np.ndarray, spec: ExitLockSpec, horizon_sec: float, *, cost_bps_values: list[float], latency_sec_values: list[float]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for cost in cost_bps_values:
        for latency in latency_sec_values:
            arrays = execution_path_arrays(canonical, horizon_sec=horizon_sec, latency_sec=float(latency))
            metrics, _, _, _ = fast_exit_lock_metrics(raw, arrays, cost_bps=float(cost), spec=spec)
            rows.append({"cost_bps": float(cost), "latency_sec": float(latency), **_jsonable(metrics)})
    return pd.DataFrame(rows).sort_values(["cost_bps", "latency_sec"]).reset_index(drop=True)


def _stress_summary(stress: pd.DataFrame) -> dict[str, object]:
    if stress.empty:
        return {"cells": 0, "min_mean_net_pnl_bps": 0.0, "min_total_net_pnl_bps": 0.0, "all_positive": False}
    mean = pd.to_numeric(stress["mean_net_pnl_bps"], errors="coerce").fillna(0.0)
    total = pd.to_numeric(stress["total_net_pnl_bps"], errors="coerce").fillna(0.0)
    worst_total_idx = int(total.idxmin())
    worst_mean_idx = int(mean.idxmin())
    return {
        "cells": int(len(stress)),
        "min_mean_net_pnl_bps": float(mean.min()),
        "min_total_net_pnl_bps": float(total.min()),
        "all_positive": bool((mean > 0.0).all() and (total > 0.0).all()),
        "worst_total_cell": _jsonable(stress.loc[worst_total_idx].to_dict()),
        "worst_mean_cell": _jsonable(stress.loc[worst_mean_idx].to_dict()),
    }


def _candidate_frame(combos: list[dict[str, object]]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for combo in combos:
        sig = combo["signal"]
        ex = combo["exit"]
        assert isinstance(ex, ExitLockSpec)
        rows.append({
            "alpha": float(sig["alpha"]),
            **sig["spec"].to_dict(),
            **{f"exit_{k}": v for k, v in ex.to_dict().items()},
            "family_tags": ";".join(combo["tags"]),
            **_jsonable(combo["metrics"]),
        })
    return pd.DataFrame(rows).sort_values(["total_net_pnl_bps", "mean_net_pnl_bps"], ascending=False).reset_index(drop=True)


def _sparse_exit_family_shift_null(
    *,
    selected: dict[str, object],
    combos: list[dict[str, object]],
    arrays,
    cost_bps: float,
    horizon_sec: float,
    shift_null_runs: int,
    min_trades: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    selected_signal = selected["signal"]
    selected_exit = selected["exit"]
    subsets = {
        "selected_only": [selected],
        "alpha_family": [c for c in combos if "alpha_family" in c["tags"] and _same_exit(c["exit"], selected_exit)],
        "ofi_family": [c for c in combos if "ofi_family" in c["tags"] and _same_exit(c["exit"], selected_exit)],
        "kline_family": [c for c in combos if "kline_family" in c["tags"] and _same_exit(c["exit"], selected_exit)],
        "exit_family": [c for c in combos if _same_signal(c["signal"], selected_signal)],
        "signal_union_family": [c for c in combos if _same_exit(c["exit"], selected_exit)],
        "full_signal_exit_union_family": combos,
    }
    selected_total = float(selected["metrics"].get("total_net_pnl_bps", 0.0))
    selected_mean = float(selected["metrics"].get("mean_net_pnl_bps", 0.0))
    n = len(np.asarray(selected["raw"], dtype=int))
    shifts = _shift_values(n=n, shifts=int(shift_null_runs), min_shift=max(1, int(round(float(horizon_sec) / 0.5))))

    # Deduplicate the 162 signal/exit combinations into 27 signal paths and 6 exit paths.
    # For any fixed shifted signal path, the non-overlap acceptance set is independent of
    # the exit policy because reserve_horizon=True.  This reduces the 1000-shift union null
    # from repeated Python path scans to small vectorized PnL lookups.
    unique_signals: dict[int, dict[str, object]] = {}
    for c in combos:
        unique_signals[id(c["signal"])] = c["signal"]
    signal_locations = {sid: _nonzero_signal_locations(np.asarray(sig["raw"], dtype=int)) for sid, sig in unique_signals.items()}

    pnl_cache: dict[tuple[float, float, bool], tuple[np.ndarray, np.ndarray]] = {}
    for c in combos:
        ex = c["exit"]
        assert isinstance(ex, ExitLockSpec)
        key = _exit_key(ex)
        if key not in pnl_cache:
            pnl_cache[key] = _precompute_exit_pnl_by_row(arrays, cost_bps=cost_bps, spec=ex)

    rows: list[dict[str, object]] = []
    exceed = {name: {"total": 0, "mean": 0} for name in subsets}
    maxima = {name: {"total": -np.inf, "mean": -np.inf, "trades": 0} for name in subsets}
    for shift in shifts:
        accepted_cache: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        for sid, (idx, sig) in signal_locations.items():
            accepted_cache[sid] = _accepted_shift_positions(idx, sig, int(shift), arrays)

        combo_metrics: dict[int, dict[str, float]] = {}
        for c in combos:
            rows_idx, dirs = accepted_cache[id(c["signal"])]
            p_long, p_short = pnl_cache[_exit_key(c["exit"])]
            combo_metrics[id(c)] = _metrics_from_accepted(rows_idx, dirs, p_long, p_short, n)

        row: dict[str, object] = {"shift_rows": int(shift)}
        for name, subset in subsets.items():
            best_total = -np.inf
            best_mean = -np.inf
            best_trades = 0
            best_total_constrained = -np.inf
            best_mean_constrained = -np.inf
            for c in subset:
                metrics = combo_metrics[id(c)]
                trades = int(metrics["trades"])
                total = float(metrics["total_net_pnl_bps"])
                mean = float(metrics["mean_net_pnl_bps"])
                if total > best_total:
                    best_total = total
                if mean > best_mean:
                    best_mean = mean
                    best_trades = trades
                if trades >= min_trades:
                    best_total_constrained = max(best_total_constrained, total)
                    best_mean_constrained = max(best_mean_constrained, mean)
            if not np.isfinite(best_total):
                best_total = 0.0
            if not np.isfinite(best_mean):
                best_mean = 0.0
            if not np.isfinite(best_total_constrained):
                best_total_constrained = 0.0
            if not np.isfinite(best_mean_constrained):
                best_mean_constrained = 0.0
            row[f"{name}_max_total_bps"] = float(best_total)
            row[f"{name}_max_mean_bps"] = float(best_mean)
            row[f"{name}_max_mean_trades"] = int(best_trades)
            row[f"{name}_max_total_bps_constrained"] = float(best_total_constrained)
            row[f"{name}_max_mean_bps_constrained"] = float(best_mean_constrained)
            maxima[name]["total"] = max(float(maxima[name]["total"]), float(best_total))
            maxima[name]["mean"] = max(float(maxima[name]["mean"]), float(best_mean))
            maxima[name]["trades"] = max(int(maxima[name]["trades"]), int(best_trades))
            if best_total >= selected_total:
                exceed[name]["total"] += 1
            if best_mean >= selected_mean:
                exceed[name]["mean"] += 1
        rows.append(row)
    df = pd.DataFrame(rows)
    denom = len(df) + 1
    summary: dict[str, object] = {
        "selected_total_net_pnl_bps": selected_total,
        "selected_mean_net_pnl_bps": selected_mean,
        "shift_null_runs": int(len(df)),
    }
    for name, subset in subsets.items():
        summary[name] = {
            "candidate_count": int(len(subset)),
            "shifts": int(len(df)),
            "selected_total_net_pnl_bps": selected_total,
            "selected_mean_net_pnl_bps": selected_mean,
            "null_total_max_bps": float(maxima[name]["total"]),
            "null_mean_max_bps": float(maxima[name]["mean"]),
            "max_mean_trade_count": int(maxima[name]["trades"]),
            "exceed_total_count": int(exceed[name]["total"]),
            "exceed_mean_count": int(exceed[name]["mean"]),
            "addone_p_total_ge_selected": float((exceed[name]["total"] + 1) / denom),
            "addone_p_mean_ge_selected": float((exceed[name]["mean"] + 1) / denom),
        }
    return df, summary


def _accepted_shift_positions(original_idx: np.ndarray, sig: np.ndarray, shift: int, arrays) -> tuple[np.ndarray, np.ndarray]:
    ts, _bid, _ask, _entry_idx, _exit_idx, _valid, horizon_ns = arrays
    n = len(ts)
    if n == 0 or len(original_idx) == 0:
        return np.asarray([], dtype=int), np.asarray([], dtype=int)
    shifted = (original_idx + int(shift)) % n
    order = np.argsort(shifted, kind="mergesort")
    out_idx: list[int] = []
    out_sig: list[int] = []
    next_allowed = -10**30
    for i, direction in zip(shifted[order], sig[order]):
        ii = int(i)
        if int(ts[ii]) < next_allowed:
            continue
        out_idx.append(ii)
        out_sig.append(int(direction))
        next_allowed = int(ts[ii]) + int(horizon_ns)
    return np.asarray(out_idx, dtype=int), np.asarray(out_sig, dtype=int)


def _metrics_from_accepted(rows_idx: np.ndarray, dirs: np.ndarray, p_long: np.ndarray, p_short: np.ndarray, n_events: int) -> dict[str, float]:
    if len(rows_idx) == 0:
        return {"events": float(n_events), "trades": 0.0, "hit_rate": 0.0, "mean_net_pnl_bps": 0.0, "total_net_pnl_bps": 0.0}
    pnl = np.where(dirs > 0, p_long[rows_idx], p_short[rows_idx]).astype(float)
    pnl = pnl[np.isfinite(pnl)]
    if len(pnl) == 0:
        return {"events": float(n_events), "trades": 0.0, "hit_rate": 0.0, "mean_net_pnl_bps": 0.0, "total_net_pnl_bps": 0.0}
    return {
        "events": float(n_events),
        "trades": float(len(pnl)),
        "hit_rate": float((pnl > 0.0).mean()),
        "mean_net_pnl_bps": float(pnl.mean()),
        "total_net_pnl_bps": float(pnl.sum()),
    }

def _precompute_exit_pnl_by_row(arrays, *, cost_bps: float, spec: ExitLockSpec) -> tuple[np.ndarray, np.ndarray]:
    ts, bid, ask, entry_idx, exit_idx, valid, _horizon_ns = arrays
    n = len(ts)
    p_long = np.full(n, np.nan, dtype=float)
    p_short = np.full(n, np.nan, dtype=float)
    tp_on = spec.has_take_profit
    sl_on = spec.has_stop_loss
    tp_bps = float(spec.take_profit_bps)
    sl_bps = float(spec.stop_loss_bps)
    for i in range(n):
        if not bool(valid[i]):
            continue
        ei = int(entry_idx[i])
        xi = int(exit_idx[i])
        if xi <= ei:
            continue
        # Long path.
        ep = float(ask[ei])
        if np.isfinite(ep) and ep > 0.0:
            tp_px = ep * (1.0 + tp_bps / 10000.0) if tp_on else np.inf
            sl_px = ep * (1.0 - sl_bps / 10000.0) if sl_on else -np.inf
            x = xi
            for j in range(ei + 1, xi + 1):
                if sl_on and float(bid[j]) <= sl_px:
                    x = j
                    break
                if tp_on and float(bid[j]) >= tp_px:
                    x = j
                    break
            xp = float(bid[x])
            if np.isfinite(xp) and xp > 0.0:
                p_long[i] = (xp - ep) / ep * 10000.0 - float(cost_bps)
        # Short path.
        ep = float(bid[ei])
        if np.isfinite(ep) and ep > 0.0:
            tp_px = ep * (1.0 - tp_bps / 10000.0) if tp_on else -np.inf
            sl_px = ep * (1.0 + sl_bps / 10000.0) if sl_on else np.inf
            x = xi
            for j in range(ei + 1, xi + 1):
                if sl_on and float(ask[j]) >= sl_px:
                    x = j
                    break
                if tp_on and float(ask[j]) <= tp_px:
                    x = j
                    break
            xp = float(ask[x])
            if np.isfinite(xp) and xp > 0.0:
                p_short[i] = (ep - xp) / ep * 10000.0 - float(cost_bps)
    return p_long, p_short


def _sparse_shift_exit_metrics(original_idx: np.ndarray, sig: np.ndarray, shift: int, arrays, p_long: np.ndarray, p_short: np.ndarray) -> dict[str, float]:
    ts, _bid, _ask, _entry_idx, _exit_idx, _valid, horizon_ns = arrays
    n = len(ts)
    if n == 0 or len(original_idx) == 0:
        return {"events": float(n), "trades": 0.0, "hit_rate": 0.0, "mean_net_pnl_bps": 0.0, "total_net_pnl_bps": 0.0}
    shifted = (original_idx + int(shift)) % n
    order = np.argsort(shifted, kind="mergesort")
    pnls: list[float] = []
    next_allowed = -10**30
    for i, direction in zip(shifted[order], sig[order]):
        ii = int(i)
        if int(ts[ii]) < next_allowed:
            continue
        pnl = float(p_long[ii] if int(direction) > 0 else p_short[ii])
        if np.isfinite(pnl):
            pnls.append(pnl)
            next_allowed = int(ts[ii]) + int(horizon_ns)
    arr = np.asarray(pnls, dtype=float)
    if len(arr) == 0:
        return {"events": float(n), "trades": 0.0, "hit_rate": 0.0, "mean_net_pnl_bps": 0.0, "total_net_pnl_bps": 0.0}
    return {
        "events": float(n),
        "trades": float(len(arr)),
        "hit_rate": float((arr > 0.0).mean()),
        "mean_net_pnl_bps": float(arr.mean()),
        "total_net_pnl_bps": float(arr.sum()),
    }


def _nonzero_signal_locations(raw: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    idx = np.flatnonzero(raw)
    return idx.astype(int), raw[idx].astype(int)


def _aggregate(*, selected_metrics, folds, bootstrap, stability, path, stress_summary, family_null, gate: ExecutionProfitLockGate) -> dict[str, object]:
    agg: dict[str, object] = {
        "trades": int(selected_metrics.get("trades", 0)),
        "hit_rate": float(selected_metrics.get("hit_rate", 0.0)),
        "mean_net_pnl_bps": float(selected_metrics.get("mean_net_pnl_bps", 0.0)),
        "median_net_pnl_bps": float(selected_metrics.get("median_net_pnl_bps", 0.0)),
        "total_net_pnl_bps": float(selected_metrics.get("total_net_pnl_bps", 0.0)),
        "profit_factor": float(selected_metrics.get("profit_factor", 0.0)),
        "max_drawdown_bps": float(selected_metrics.get("max_drawdown_bps", 0.0)),
        "take_profit_exits": int(selected_metrics.get("take_profit_exits", 0)),
        "stop_loss_exits": int(selected_metrics.get("stop_loss_exits", 0)),
        "horizon_exits": int(selected_metrics.get("horizon_exits", 0)),
        "mean_hold_sec": float(selected_metrics.get("mean_hold_sec", 0.0)),
        "folds_with_trades": int((folds["trades"].astype(float) > 0).sum()) if not folds.empty else 0,
        "fold_min_mean_net_pnl_bps": float(folds["mean_net_pnl_bps"].min()) if not folds.empty else 0.0,
        "fold_min_total_net_pnl_bps": float(folds["total_net_pnl_bps"].min()) if not folds.empty else 0.0,
        "bootstrap_mean_p05_bps": float(bootstrap.get("mean_p05_bps", 0.0)),
        "bootstrap_total_p05_bps": float(bootstrap.get("total_p05_bps", 0.0)),
        "positive_equal_trade_blocks_5": int(stability.get("positive_equal_trade_blocks_5", 0)),
        "positive_equal_trade_blocks_10": int(stability.get("positive_equal_trade_blocks_10", 0)),
        "equal_trade_block_5_min_total_bps": float(stability.get("equal_trade_block_5_min_total_bps", 0.0)),
        "equal_trade_block_10_min_total_bps": float(stability.get("equal_trade_block_10_min_total_bps", 0.0)),
        "top5_winner_removed_total_bps": float(path.get("top5_winner_removed_total_bps", 0.0)),
        "top7_winner_removed_total_bps": float(path.get("top7_winner_removed_total_bps", 0.0)),
        "configured_top_winner_removal_k": int(gate.min_top_winner_removal_k),
        "configured_top_winner_removed_total_bps": _top_removal_total(path, gate.min_top_winner_removal_k),
        "leave_one_trade_out_min_total_bps": float(path.get("leave_one_trade_out_min_total_bps", 0.0)),
        "leave_one_fold_out_min_total_bps": float(path.get("leave_one_fold_out_min_total_bps", 0.0)),
        "stress_cells": int(stress_summary.get("cells", 0)),
        "stress_all_positive": bool(stress_summary.get("all_positive", False)),
        "stress_all_min_mean_net_pnl_bps": float(stress_summary.get("min_mean_net_pnl_bps", 0.0)),
        "stress_all_min_total_net_pnl_bps": float(stress_summary.get("min_total_net_pnl_bps", 0.0)),
    }
    family_names = ["selected_only", "alpha_family", "ofi_family", "kline_family", "exit_family", "signal_union_family", "full_signal_exit_union_family"]
    for name in family_names:
        fam = family_null.get(name, {})
        agg[f"{name}_addone_p_total"] = float(fam.get("addone_p_total_ge_selected", 1.0))
        agg[f"{name}_addone_p_mean"] = float(fam.get("addone_p_mean_ge_selected", 1.0))
        agg[f"{name}_null_max_total_bps"] = float(fam.get("null_total_max_bps", 0.0))
        agg[f"{name}_null_max_mean_bps"] = float(fam.get("null_mean_max_bps", 0.0))

    checks: dict[str, bool] = {}
    checks["enough_oof_trades"] = int(agg["trades"]) >= gate.min_oof_trades
    checks["enough_folds_with_trades"] = int(agg["folds_with_trades"]) >= gate.min_folds_with_trades
    checks["positive_fold_min_mean"] = float(agg["fold_min_mean_net_pnl_bps"]) > gate.min_fold_mean_net_bps
    checks["positive_fold_min_total"] = float(agg["fold_min_total_net_pnl_bps"]) > gate.min_fold_total_net_bps
    checks["positive_bootstrap_mean_p05"] = float(agg["bootstrap_mean_p05_bps"]) > gate.min_bootstrap_mean_p05_bps
    checks["positive_equal_trade_blocks_5"] = int(agg["positive_equal_trade_blocks_5"]) >= gate.min_equal_trade_blocks_5_positive
    checks["positive_equal_trade_blocks_10"] = int(agg["positive_equal_trade_blocks_10"]) >= gate.min_equal_trade_blocks_10_positive
    checks["top_winner_removal_ok"] = float(agg["configured_top_winner_removed_total_bps"]) > gate.min_top_winner_removed_total_bps
    checks["leave_one_trade_out_ok"] = float(agg["leave_one_trade_out_min_total_bps"]) > 0.0
    checks["leave_one_fold_out_ok"] = float(agg["leave_one_fold_out_min_total_bps"]) > 0.0
    checks["full_severe_stress_ok"] = bool(agg["stress_all_positive"]) and float(agg["stress_all_min_mean_net_pnl_bps"]) > gate.min_full_stress_mean_net_bps and float(agg["stress_all_min_total_net_pnl_bps"]) > gate.min_full_stress_total_net_bps
    for name in family_names:
        checks[f"{name}_addone_total_ok"] = float(agg[f"{name}_addone_p_total"]) <= gate.max_addone_family_p
        checks[f"{name}_addone_mean_ok"] = float(agg[f"{name}_addone_p_mean"]) <= gate.max_addone_family_p
    agg["gate"] = {"passed": bool(all(checks.values())), "checks": checks, "failed_checks": [k for k, v in checks.items() if not v]}
    return agg


def _top_removal_total(path: dict[str, object], k: int) -> float:
    rows = path.get("top_winner_removal", [])
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and int(row.get("removed_top_winners", -1)) == int(k):
                return float(row.get("remaining_total_net_pnl_bps", 0.0))
    return float(path.get("top5_winner_removed_total_bps", 0.0))


def _same_signal(left: dict[str, object], right: dict[str, object]) -> bool:
    return _key(left["alpha"], left["spec"]) == _key(right["alpha"], right["spec"])


def _same_exit(left: object, right: object) -> bool:
    return isinstance(left, ExitLockSpec) and isinstance(right, ExitLockSpec) and _exit_key(left) == _exit_key(right)


def _exit_key(spec: ExitLockSpec) -> tuple[float, float, bool]:
    return (round(float(spec.take_profit_bps), 12), round(float(spec.stop_loss_bps), 12), bool(spec.reserve_horizon))


def _dedupe_exit_specs(specs: list[ExitLockSpec]) -> list[ExitLockSpec]:
    out: list[ExitLockSpec] = []
    seen: set[tuple[float, float, bool]] = set()
    for spec in specs:
        key = _exit_key(spec)
        if key not in seen:
            out.append(spec)
            seen.add(key)
    return out


def _write_report(path: Path, result: dict[str, object], folds: pd.DataFrame, candidates: pd.DataFrame, stress: pd.DataFrame) -> None:
    """Write a compact report without expensive rich formatting."""
    agg = result["aggregate"]
    fam = result["family_null"]
    selected = {
        "signal": result["selected_signal_spec"],
        "exit": result["selected_exit_spec"],
    }
    fold_cols = [c for c in ["fold", "trades", "hit_rate", "mean_net_pnl_bps", "total_net_pnl_bps", "take_profit_exits", "horizon_exits"] if c in folds.columns]
    stress_cols = [c for c in ["cost_bps", "latency_sec", "trades", "mean_net_pnl_bps", "total_net_pnl_bps", "take_profit_exits"] if c in stress.columns]
    leader_cols = [c for c in ["alpha", "ofi_col", "ofi_quantile", "kline_col", "kline_quantile", "exit_take_profit_bps", "family_tags", "trades", "hit_rate", "mean_net_pnl_bps", "total_net_pnl_bps"] if c in candidates.columns]
    lines = [
        "# V17 Execution Profit-Lock Certificate",
        "",
        "V17 keeps the V15/V16 entry policy frozen and adds only a slot-preserving take-profit exit lock. The original 90s slot remains reserved after early exit.",
        "",
        "## Selected frozen policy",
        "",
        "```json",
        json.dumps(selected, indent=2),
        "```",
        "",
        "## Gate and aggregate",
        "",
        "```json",
        json.dumps(agg, indent=2),
        "```",
        "",
        "## Fold metrics",
        "",
        folds[fold_cols].to_csv(index=False).strip() if fold_cols else "No fold metrics.",
        "",
        "## Severe stress grid",
        "",
        stress[stress_cols].to_csv(index=False).strip() if stress_cols else "No stress metrics.",
        "",
        "## Family null summary",
        "",
        "```json",
        json.dumps(fam, indent=2),
        "```",
        "",
        "## Candidate leaderboard top 30",
        "",
        candidates[leader_cols].head(30).to_csv(index=False).strip() if leader_cols else "No candidates.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
