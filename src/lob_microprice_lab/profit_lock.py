
from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .kline_guard import KlineGuardSpec
from .profit_stability import _prepare_execution_arrays
from .profit_success_fast import _candidate, _family_specs, _load_alpha_data
from .selective import backtest_fixed_signals_taker_bidask_non_overlapping, stress_fixed_signals
from .slot_veto import _shift_values
from .stress import block_bootstrap_pnl


@dataclass(frozen=True)
class ProfitLockGate:
    """V16 frozen-policy profit lock gate.

    V16 is intentionally a certificate layer, not a new tuning layer.  It freezes the promoted V15
    policy and audits it with stricter shifted-signal p-values, larger stress grids, and
    winner-dependence checks.
    """

    min_oof_trades: int = 20
    min_folds_with_trades: int = 5
    min_fold_mean_net_bps: float = 0.0
    min_fold_total_net_bps: float = 0.0
    min_bootstrap_mean_p05_bps: float = 0.0
    max_addone_family_p: float = 0.01
    min_top_winner_removal_k: int = 5
    min_top_winner_removed_total_bps: float = 0.0
    max_primary_stress_cost_bps: float = 7.5
    max_primary_stress_latency_sec: float = 5.0
    max_secondary_stress_cost_bps: float = 10.0
    max_secondary_stress_latency_sec: float = 3.0
    min_stress_mean_net_bps: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_profit_lock_certificate(
    *,
    base_ensemble_dir: str | Path,
    kline_ensemble_dir: str | Path,
    out_dir: str | Path,
    horizon_sec: float = 90.0,
    cost_bps: float = 1.5,
    latency_sec: float = 0.5,
    selected_spec: KlineGuardSpec | None = None,
    alpha_grid: list[float] | None = None,
    ofi_cols: list[str] | None = None,
    ofi_quantiles: list[float] | None = None,
    kline_cols: list[str] | None = None,
    kline_quantiles: list[float] | None = None,
    stress_cost_bps_values: list[float] | None = None,
    stress_latency_sec_values: list[float] | None = None,
    shift_null_runs: int = 1000,
    gate: ProfitLockGate | None = None,
    clean: bool = False,
) -> dict[str, object]:
    base = Path(base_ensemble_dir)
    kline = Path(kline_ensemble_dir)
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    selected_spec = selected_spec or KlineGuardSpec(
        edge_threshold=0.1,
        kline_alpha=0.125,
        ofi_col="ofi_sum_l5_norm",
        ofi_quantile=0.9,
        kline_col="kline_15s_rv_6_bps",
        kline_quantile=0.0,
        kline_operator=">=",
        directional=True,
    )
    alpha_grid = _dedupe(alpha_grid or [0.0, 0.025, 0.05, 0.075, 0.1, 0.125, 0.15])
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
    stress_cost_bps_values = _dedupe(stress_cost_bps_values or [1.5, 3.0, 5.0, 7.5, 10.0])
    stress_latency_sec_values = _dedupe(stress_latency_sec_values or [0.0, 0.5, 1.0, 2.0, 3.0, 5.0])
    gate = gate or ProfitLockGate()

    specs = _family_specs(selected_spec, alpha_grid, ofi_cols, ofi_quantiles, kline_cols, kline_quantiles)
    required = sorted({selected_spec.ofi_col, selected_spec.kline_col, *ofi_cols, *kline_cols})
    alphas = sorted({float(alpha) for alpha, _, _ in specs})
    data = _load_alpha_data(base, kline, alphas, required, selected_spec.edge_threshold, horizon_sec, cost_bps, latency_sec)

    canonical = data[float(selected_spec.kline_alpha)]["oof"].copy()
    arrays = _prepare_execution_arrays(canonical, horizon_sec=horizon_sec, latency_sec=latency_sec)

    candidates: list[dict[str, object]] = []
    selected: dict[str, object] | None = None
    for alpha, spec, tags in specs:
        cand = _candidate(float(alpha), spec, tags, data[float(alpha)], arrays, cost_bps, horizon_sec, latency_sec)
        candidates.append(cand)
        if _same_key(float(alpha), spec, float(selected_spec.kline_alpha), selected_spec):
            selected = cand
    if selected is None:
        raise RuntimeError("selected V15 policy was not generated")

    selected_oof = canonical.copy()
    selected_oof["signal"] = np.asarray(selected["raw"], dtype=int)
    selected_bt, selected_metrics = backtest_fixed_signals_taker_bidask_non_overlapping(
        selected_oof,
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
    )
    selected_bt["fold"] = canonical["fold"].to_numpy()
    selected_bt.to_csv(out / "profit_lock_oof_backtest.csv", index=False)

    folds = pd.DataFrame(selected["fold_rows"]).sort_values("fold").reset_index(drop=True)
    folds.to_csv(out / "fold_metrics.csv", index=False)

    candidate_rows = []
    for cand in candidates:
        spec = cand["spec"]
        row = spec.to_dict()
        row.update({
            "alpha": float(cand["alpha"]),
            "family_tags": ";".join(cand["tags"]),
            **cand["metrics"],
        })
        candidate_rows.append(row)
    candidate_df = pd.DataFrame(candidate_rows).sort_values(["total_net_pnl_bps", "mean_net_pnl_bps"], ascending=False)
    candidate_df.to_csv(out / "profit_lock_family_candidates.csv", index=False)

    trades = selected_bt.loc[selected_bt["traded"].astype(int) == 1].reset_index(drop=True)
    pnl = pd.to_numeric(trades["net_pnl_bps"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    bootstrap = block_bootstrap_pnl(pnl, iterations=5000, block_size=5, seed=56016)
    path = _path_diagnostics(pnl, trades["fold"].to_numpy(dtype=int) if "fold" in trades.columns else np.asarray([], dtype=int))

    stress = stress_fixed_signals(
        selected_oof,
        horizon_sec=horizon_sec,
        cost_bps_values=stress_cost_bps_values,
        latency_sec_values=stress_latency_sec_values,
    ).sort_values(["cost_bps", "latency_sec"]).reset_index(drop=True)
    stress.to_csv(out / "profit_lock_extended_stress.csv", index=False)
    stress_summary = _stress_summary(stress, gate)

    null_df, family_null = sparse_family_shift_null(
        selected=selected,
        candidates=candidates,
        arrays=arrays,
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        shift_null_runs=shift_null_runs,
        min_trades=gate.min_oof_trades,
    )
    null_df.to_csv(out / "profit_lock_sparse_family_shift_null.csv", index=False)

    aggregate = _aggregate(
        selected_metrics=selected_metrics,
        folds=folds,
        bootstrap=bootstrap,
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
        "selected_spec": selected_spec.to_dict(),
        "alpha_grid": [float(x) for x in alpha_grid],
        "ofi_cols": [str(x) for x in ofi_cols],
        "ofi_quantiles": [float(x) for x in ofi_quantiles],
        "kline_cols": [str(x) for x in kline_cols],
        "kline_quantiles": [float(x) for x in kline_quantiles],
        "stress_cost_bps_values": [float(x) for x in stress_cost_bps_values],
        "stress_latency_sec_values": [float(x) for x in stress_latency_sec_values],
        "shift_null_runs": int(len(null_df)),
        "gate_config": gate.to_dict(),
        "selected_metrics": _jsonable(selected_metrics),
        "bootstrap": _jsonable(bootstrap),
        "path_diagnostics": _jsonable(path),
        "stress_summary": _jsonable(stress_summary),
        "family_null": _jsonable(family_null),
        "aggregate": _jsonable(aggregate),
        "out_dir": str(out),
    }
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    _write_report(out / "REPORT.md", result, folds, candidate_df, stress)
    return result


def sparse_family_shift_null(
    *,
    selected: dict[str, object],
    candidates: list[dict[str, object]],
    arrays: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, int],
    cost_bps: float,
    horizon_sec: float,
    shift_null_runs: int,
    min_trades: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    selected_total = float(selected["metrics"].get("total_net_pnl_bps", 0.0))
    selected_mean = float(selected["metrics"].get("mean_net_pnl_bps", 0.0))
    subsets = {
        "selected_only": [selected],
        "alpha_family": [cand for cand in candidates if "alpha_family" in cand["tags"]],
        "ofi_family": [cand for cand in candidates if "ofi_family" in cand["tags"]],
        "kline_family": [cand for cand in candidates if "kline_family" in cand["tags"]],
        "triple_union_family": candidates,
    }
    n = len(np.asarray(selected["raw"], dtype=int))
    min_shift = max(1, int(round(float(horizon_sec) / 0.5)))
    shifts = _shift_values(n=n, shifts=int(shift_null_runs), min_shift=min_shift)
    locations = {id(cand): _nonzero_signal_locations(np.asarray(cand["raw"], dtype=int)) for cand in candidates}

    rows: list[dict[str, object]] = []
    exceed = {name: {"total": 0, "mean": 0} for name in subsets}
    maxima = {name: {"total": -np.inf, "mean": -np.inf, "trades": 0} for name in subsets}
    for shift in shifts:
        row: dict[str, object] = {"shift_rows": int(shift)}
        for name, subset in subsets.items():
            best_total = -np.inf
            best_mean = -np.inf
            best_trades = 0
            best_total_constrained = -np.inf
            best_mean_constrained = -np.inf
            for cand in subset:
                idx, sig = locations[id(cand)]
                metrics = _sparse_shift_metrics(idx, sig, shift, arrays, cost_bps)
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
    summary: dict[str, object] = {}
    for name in subsets:
        summary[name] = {
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


def assert_sparse_matches_dense(
    raw: np.ndarray,
    arrays: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, int],
    *,
    cost_bps: float,
    shifts: list[int],
) -> None:
    from .profit_stability import _fast_signal_metrics

    idx, sig = _nonzero_signal_locations(np.asarray(raw, dtype=int))
    for shift in shifts:
        dense, _ = _fast_signal_metrics(np.roll(raw, int(shift)), arrays, cost_bps=cost_bps)
        sparse = _sparse_shift_metrics(idx, sig, int(shift), arrays, cost_bps)
        for key in ["trades", "hit_rate", "mean_net_pnl_bps", "total_net_pnl_bps"]:
            if not np.isclose(float(dense[key]), float(sparse[key]), atol=1e-10, rtol=0):
                raise AssertionError(f"sparse mismatch at shift {shift} key {key}: dense={dense[key]} sparse={sparse[key]}")


def _nonzero_signal_locations(raw: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    idx = np.flatnonzero(raw)
    return idx.astype(int), raw[idx].astype(int)


def _sparse_shift_metrics(
    original_idx: np.ndarray,
    sig: np.ndarray,
    shift: int,
    arrays: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, int],
    cost_bps: float,
) -> dict[str, float]:
    ts, bid, ask, entry_idx, exit_idx, valid, horizon_ns = arrays
    n = len(ts)
    if n == 0 or len(original_idx) == 0:
        return {"events": float(n), "trades": 0.0, "hit_rate": 0.0, "mean_net_pnl_bps": 0.0, "total_net_pnl_bps": 0.0}
    shifted = (original_idx + int(shift)) % n
    order = np.argsort(shifted, kind="mergesort")
    pnls: list[float] = []
    next_allowed = -10**30
    for i, direction in zip(shifted[order], sig[order]):
        ii = int(i)
        if int(ts[ii]) < next_allowed or not bool(valid[ii]):
            continue
        ei = int(entry_idx[ii])
        xi = int(exit_idx[ii])
        if int(direction) > 0:
            ep = float(ask[ei])
            xp = float(bid[xi])
            pnl = (xp - ep) / ep * 10000.0
        else:
            ep = float(bid[ei])
            xp = float(ask[xi])
            pnl = (ep - xp) / ep * 10000.0
        if np.isfinite(ep) and np.isfinite(xp) and ep > 0 and xp > 0:
            pnls.append(float(pnl) - float(cost_bps))
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


def _path_diagnostics(pnl: np.ndarray, folds: np.ndarray) -> dict[str, object]:
    pnl = np.asarray(pnl, dtype=float)
    if len(pnl) == 0:
        return {}
    total = float(pnl.sum())
    winners = np.sort(pnl[pnl > 0])[::-1]
    top_removal = []
    for k in range(1, min(10, len(winners)) + 1):
        rem = float(total - winners[:k].sum())
        top_removal.append({
            "removed_top_winners": int(k),
            "removed_winner_sum_bps": float(winners[:k].sum()),
            "remaining_total_net_pnl_bps": rem,
            "remaining_mean_net_pnl_bps": float(rem / max(1, len(pnl) - k)),
        })
    jackknife = []
    for i in range(len(pnl)):
        remaining = np.delete(pnl, i)
        jackknife.append({"removed_trade_index": int(i), "remaining_total_net_pnl_bps": float(remaining.sum())})
    fold_loo = []
    if len(folds) == len(pnl):
        for fold in sorted(set(int(x) for x in folds)):
            remaining = pnl[folds != fold]
            fold_loo.append({
                "removed_fold": int(fold),
                "remaining_trades": int(len(remaining)),
                "remaining_total_net_pnl_bps": float(remaining.sum()),
                "remaining_mean_net_pnl_bps": float(remaining.mean()) if len(remaining) else 0.0,
            })
    rolling = []
    for window in [3, 5, 10]:
        if len(pnl) >= window:
            vals = np.convolve(pnl, np.ones(window), "valid")
            rolling.append({"window_trades": int(window), "min_total_net_pnl_bps": float(vals.min()), "max_total_net_pnl_bps": float(vals.max())})
    return {
        "trade_count": int(len(pnl)),
        "total_net_pnl_bps": total,
        "mean_net_pnl_bps": float(pnl.mean()),
        "median_net_pnl_bps": float(np.median(pnl)),
        "min_trade_net_pnl_bps": float(pnl.min()),
        "max_trade_net_pnl_bps": float(pnl.max()),
        "positive_trades": int((pnl > 0).sum()),
        "negative_or_zero_trades": int((pnl <= 0).sum()),
        "top_winner_removal": top_removal,
        "top5_winner_removed_total_bps": _top_removed_from_list(top_removal, 5),
        "top7_winner_removed_total_bps": _top_removed_from_list(top_removal, 7),
        "leave_one_trade_out_min_total_bps": float(min(x["remaining_total_net_pnl_bps"] for x in jackknife)),
        "leave_one_fold_out": fold_loo,
        "leave_one_fold_out_min_total_bps": float(min([x["remaining_total_net_pnl_bps"] for x in fold_loo]) if fold_loo else 0.0),
        "rolling_windows": rolling,
    }


def _top_removed_from_list(rows: list[dict[str, object]], k: int) -> float:
    for row in rows:
        if int(row["removed_top_winners"]) == int(k):
            return float(row["remaining_total_net_pnl_bps"])
    return 0.0


def _stress_summary(stress: pd.DataFrame, gate: ProfitLockGate) -> dict[str, object]:
    if stress.empty:
        return {}
    primary = stress[(stress["cost_bps"].astype(float) <= gate.max_primary_stress_cost_bps) & (stress["latency_sec"].astype(float) <= gate.max_primary_stress_latency_sec)]
    secondary = stress[(stress["cost_bps"].astype(float) <= gate.max_secondary_stress_cost_bps) & (stress["latency_sec"].astype(float) <= gate.max_secondary_stress_latency_sec)]
    worst = stress.sort_values(["mean_net_pnl_bps", "total_net_pnl_bps"]).head(1).to_dict("records")
    return {
        "cells": int(len(stress)),
        "min_mean_net_pnl_bps": float(stress["mean_net_pnl_bps"].min()),
        "min_total_net_pnl_bps": float(stress["total_net_pnl_bps"].min()),
        "positive_mean_cells": int((stress["mean_net_pnl_bps"] > 0).sum()),
        "positive_total_cells": int((stress["total_net_pnl_bps"] > 0).sum()),
        "primary_cells": int(len(primary)),
        "primary_min_mean_net_pnl_bps": float(primary["mean_net_pnl_bps"].min()),
        "primary_min_total_net_pnl_bps": float(primary["total_net_pnl_bps"].min()),
        "primary_positive_cells": int((primary["mean_net_pnl_bps"] > 0).sum()),
        "secondary_cells": int(len(secondary)),
        "secondary_min_mean_net_pnl_bps": float(secondary["mean_net_pnl_bps"].min()),
        "secondary_min_total_net_pnl_bps": float(secondary["total_net_pnl_bps"].min()),
        "secondary_positive_cells": int((secondary["mean_net_pnl_bps"] > 0).sum()),
        "absolute_worst_cell": worst[0] if worst else {},
    }


def _aggregate(*, selected_metrics, folds, bootstrap, path, stress_summary, family_null, gate: ProfitLockGate) -> dict[str, object]:
    agg: dict[str, object] = {
        "trades": int(selected_metrics.get("trades", 0)),
        "hit_rate": float(selected_metrics.get("hit_rate", 0.0)),
        "mean_net_pnl_bps": float(selected_metrics.get("mean_net_pnl_bps", 0.0)),
        "total_net_pnl_bps": float(selected_metrics.get("total_net_pnl_bps", 0.0)),
        "folds_with_trades": int((folds["trades"].astype(float) > 0).sum()) if not folds.empty else 0,
        "fold_min_mean_net_pnl_bps": float(folds["mean_net_pnl_bps"].min()) if not folds.empty else 0.0,
        "fold_min_total_net_pnl_bps": float(folds["total_net_pnl_bps"].min()) if not folds.empty else 0.0,
        "bootstrap_mean_p05_bps": float(bootstrap.get("mean_p05_bps", 0.0)),
        "bootstrap_total_p05_bps": float(bootstrap.get("total_p05_bps", 0.0)),
        "top5_winner_removed_total_bps": float(path.get("top5_winner_removed_total_bps", 0.0)),
        "top7_winner_removed_total_bps": float(path.get("top7_winner_removed_total_bps", 0.0)),
        "configured_top_winner_removal_k": int(gate.min_top_winner_removal_k),
        "configured_top_winner_removed_total_bps": _top_removal_total(path, gate.min_top_winner_removal_k),
        "leave_one_trade_out_min_total_bps": float(path.get("leave_one_trade_out_min_total_bps", 0.0)),
        "leave_one_fold_out_min_total_bps": float(path.get("leave_one_fold_out_min_total_bps", 0.0)),
        "stress_primary_min_mean_net_pnl_bps": float(stress_summary.get("primary_min_mean_net_pnl_bps", 0.0)),
        "stress_primary_min_total_net_pnl_bps": float(stress_summary.get("primary_min_total_net_pnl_bps", 0.0)),
        "stress_secondary_min_mean_net_pnl_bps": float(stress_summary.get("secondary_min_mean_net_pnl_bps", 0.0)),
        "stress_secondary_min_total_net_pnl_bps": float(stress_summary.get("secondary_min_total_net_pnl_bps", 0.0)),
        "stress_all_min_mean_net_pnl_bps": float(stress_summary.get("min_mean_net_pnl_bps", 0.0)),
        "stress_all_min_total_net_pnl_bps": float(stress_summary.get("min_total_net_pnl_bps", 0.0)),
    }
    for name in ["selected_only", "alpha_family", "ofi_family", "kline_family", "triple_union_family"]:
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
    checks["top_winner_removal_ok"] = float(agg["configured_top_winner_removed_total_bps"]) > gate.min_top_winner_removed_total_bps
    checks["leave_one_trade_out_ok"] = float(agg["leave_one_trade_out_min_total_bps"]) > 0.0
    checks["leave_one_fold_out_ok"] = float(agg["leave_one_fold_out_min_total_bps"]) > 0.0
    checks["primary_stress_ok"] = float(agg["stress_primary_min_mean_net_pnl_bps"]) > gate.min_stress_mean_net_bps and float(agg["stress_primary_min_total_net_pnl_bps"]) > 0.0
    checks["secondary_stress_ok"] = float(agg["stress_secondary_min_mean_net_pnl_bps"]) > gate.min_stress_mean_net_bps and float(agg["stress_secondary_min_total_net_pnl_bps"]) > 0.0
    for name in ["selected_only", "alpha_family", "ofi_family", "kline_family", "triple_union_family"]:
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


def _write_report(path: Path, result: dict[str, object], folds: pd.DataFrame, candidates: pd.DataFrame, stress: pd.DataFrame) -> None:
    agg = result["aggregate"]
    lines = [
        "# V16 Profit Lock Certificate",
        "",
        "V16 freezes the V15 promoted policy and adds stronger audit evidence. It does not retune alpha, OFI quantile, K-line feature, or K-line quantile.",
        "",
        "## Gate",
        "",
        "```json",
        json.dumps(agg.get("gate", {}), indent=2),
        "```",
        "",
        "## Aggregate",
        "",
        "```json",
        json.dumps(agg, indent=2),
        "```",
        "",
        "## Fold metrics",
        "",
        folds.to_markdown(index=False),
        "",
        "## Extended stress grid",
        "",
        stress.to_markdown(index=False),
        "",
        "## Family null summary",
        "",
        "```json",
        json.dumps(result["family_null"], indent=2),
        "```",
        "",
        "## Path diagnostics",
        "",
        "```json",
        json.dumps(result["path_diagnostics"], indent=2),
        "```",
        "",
        "## Candidate leaderboard",
        "",
        candidates.head(30).to_markdown(index=False),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _same_key(alpha: float, spec: KlineGuardSpec, selected_alpha: float, selected: KlineGuardSpec) -> bool:
    return (
        abs(float(alpha) - float(selected_alpha)) < 1e-12
        and abs(float(spec.edge_threshold) - float(selected.edge_threshold)) < 1e-12
        and spec.ofi_col == selected.ofi_col
        and abs(float(spec.ofi_quantile) - float(selected.ofi_quantile)) < 1e-12
        and spec.kline_col == selected.kline_col
        and abs(float(spec.kline_quantile) - float(selected.kline_quantile)) < 1e-12
        and spec.kline_operator == selected.kline_operator
        and bool(spec.directional) == bool(selected.directional)
    )


def _dedupe(values: list[float]) -> list[float]:
    out: list[float] = []
    seen: set[float] = set()
    for value in values:
        key = round(float(value), 12)
        if key not in seen:
            out.append(float(value))
            seen.add(key)
    return out


def _jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, tuple):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj
