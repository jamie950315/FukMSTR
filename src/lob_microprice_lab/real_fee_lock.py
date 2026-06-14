from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from .exit_lock import ExitLockSpec, backtest_fixed_signals_taker_bidask_exit_lock, execution_path_arrays
from .profit_execution_lock import _accepted_shift_positions, _metrics_from_accepted, _precompute_exit_pnl_by_row
from .profit_lock import _jsonable, _path_diagnostics
from .profit_success_fast import _stability
from .stress import block_bootstrap_pnl


@dataclass(frozen=True)
class RealFeeSpec:
    """Exchange fee schedule supplied by the user.

    Percent inputs follow exchange-style notation.  A value of 0.0400 means 0.0400%,
    which is 4 bps per filled side.  For a taker entry plus taker exit this is 8 bps
    round trip.  Maker fee is included for audit and future routing, but the promoted
    V19 route remains taker/taker because conservative maker-fill simulation did not
    improve this bundled sample.
    """

    taker_fee_percent: float = 0.0400
    maker_fee_percent: float = 0.0000

    @property
    def taker_fee_bps_per_side(self) -> float:
        return float(self.taker_fee_percent) * 100.0

    @property
    def maker_fee_bps_per_side(self) -> float:
        return float(self.maker_fee_percent) * 100.0

    @property
    def taker_taker_roundtrip_bps(self) -> float:
        return 2.0 * self.taker_fee_bps_per_side

    def to_dict(self) -> dict[str, object]:
        d = asdict(self)
        d.update({
            "taker_fee_bps_per_side": self.taker_fee_bps_per_side,
            "maker_fee_bps_per_side": self.maker_fee_bps_per_side,
            "taker_taker_roundtrip_bps": self.taker_taker_roundtrip_bps,
        })
        return d


@dataclass(frozen=True)
class FeeGuardFilterSpec:
    """One slot-preserving high-fee filter.

    transform:
      - raw: use the column value directly.
      - abs: use abs(column).
      - signed: use signal_direction * column, where direction is +1 for long and -1 for short.
    """

    transform: str
    column: str
    operator: str
    threshold: float
    quantile: float | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @property
    def key(self) -> tuple[str, str, str, float]:
        return (str(self.transform), str(self.column), str(self.operator), round(float(self.threshold), 12))


@dataclass(frozen=True)
class RealFeeLockGate:
    min_trades: int = 10
    min_hit_rate: float = 0.75
    min_mean_net_pnl_bps: float = 8.0
    min_total_net_pnl_bps: float = 100.0
    min_fold_mean_net_pnl_bps: float = 0.0
    min_fold_total_net_pnl_bps: float = 0.0
    min_bootstrap_mean_p05_bps: float = 0.0
    max_family_addone_p: float = 0.01
    max_stress_fee_side_bps: float = 7.5
    max_stress_latency_sec: float = 5.0
    min_stress_mean_net_pnl_bps: float = 0.0
    min_stress_total_net_pnl_bps: float = 0.0
    missed_trade_gate_probability: float = 0.50
    missed_trade_min_p05_total_bps: float = 0.0
    extra_cost_gate_bps: float = 10.0
    extra_cost_min_total_bps: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def default_v19_fee_filters() -> list[FeeGuardFilterSpec]:
    """Promoted V19 high-fee guard discovered after applying the user's real fee.

    These thresholds are fixed constants in the generated V19 package.  They must not
    be retuned on the same bundled sample.  They should be treated as frozen when run
    on new days.
    """

    return [
        FeeGuardFilterSpec("signed", "kline_15s_signal", ">=", -0.7266055861290821, 0.1),
        FeeGuardFilterSpec("raw", "kline_1m_rv_3_bps", "<=", 17.890597279145457, 0.7),
        FeeGuardFilterSpec("raw", "kline_1m_range_z_6", ">=", -1.3068193253455331, 0.1),
    ]


def run_real_fee_lock_certificate(
    *,
    v17_run_dir: str | Path,
    out_dir: str | Path,
    fee_spec: RealFeeSpec | None = None,
    selected_filters: list[FeeGuardFilterSpec] | None = None,
    horizon_sec: float = 90.0,
    latency_sec: float = 0.5,
    take_profit_bps: float = 40.0,
    stop_loss_bps: float = 0.0,
    candidate_quantiles: list[float] | None = None,
    max_filter_count: int = 2,
    shift_null_runs: int = 1000,
    stress_fee_side_bps_values: list[float] | None = None,
    stress_latency_sec_values: list[float] | None = None,
    random_scenarios: int = 10000,
    seed: int = 19019,
    gate: RealFeeLockGate | None = None,
    clean: bool = False,
) -> dict[str, object]:
    run = Path(v17_run_dir)
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    fee_spec = fee_spec or RealFeeSpec()
    selected_filters = selected_filters or default_v19_fee_filters()
    candidate_quantiles = _dedupe_float(candidate_quantiles or [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])
    stress_fee_side_bps_values = _dedupe_float(stress_fee_side_bps_values or [4.0, 5.0, 6.0, 7.5, 10.0])
    stress_latency_sec_values = _dedupe_float(stress_latency_sec_values or [0.0, 0.5, 1.0, 2.0, 3.0, 5.0])
    gate = gate or RealFeeLockGate()

    source_path = run / "execution_lock_oof_backtest.csv"
    if not source_path.exists():
        raise FileNotFoundError(f"missing frozen V17 ledger: {source_path}")
    frame = pd.read_csv(source_path)
    if "timestamp" not in frame.columns:
        raise ValueError("execution_lock_oof_backtest.csv must contain timestamp")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, format="mixed")
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    raw_signal = pd.to_numeric(frame.get("signal", 0), errors="coerce").fillna(0).astype(int).clip(-1, 1).to_numpy()

    cost_bps = float(fee_spec.taker_taker_roundtrip_bps)
    exit_spec = ExitLockSpec(take_profit_bps=float(take_profit_bps), stop_loss_bps=float(stop_loss_bps), reserve_horizon=True)

    selected_mask = _mask_for_filters(frame, raw_signal, selected_filters) & (raw_signal != 0)
    selected_signal = np.where(selected_mask, raw_signal, 0)
    selected_frame = frame.copy()
    selected_frame["signal"] = selected_signal
    selected_bt, selected_metrics = backtest_fixed_signals_taker_bidask_exit_lock(
        selected_frame,
        cost_bps=cost_bps,
        horizon_sec=float(horizon_sec),
        latency_sec=float(latency_sec),
        spec=exit_spec,
    )
    selected_bt["real_taker_fee_bps_per_side"] = fee_spec.taker_fee_bps_per_side
    selected_bt["real_maker_fee_bps_per_side"] = fee_spec.maker_fee_bps_per_side
    selected_bt["real_roundtrip_fee_bps"] = selected_bt["traded"].astype(float) * cost_bps
    selected_bt.to_csv(out / "real_fee_lock_oof_backtest.csv", index=False)
    trades = selected_bt.loc[selected_bt["traded"].astype(int) == 1].copy().reset_index(drop=True)
    trades.to_csv(out / "real_fee_lock_trade_ledger.csv", index=False)

    folds = _fold_metrics(trades)
    folds.to_csv(out / "fold_metrics.csv", index=False)
    bootstrap = block_bootstrap_pnl(pd.to_numeric(trades.get("net_pnl_bps", 0), errors="coerce").fillna(0.0).to_numpy(dtype=float), iterations=5000, block_size=5, seed=seed)
    stability = _stability(selected_bt)
    path = _path_diagnostics(pd.to_numeric(trades.get("net_pnl_bps", 0), errors="coerce").fillna(0.0).to_numpy(dtype=float), pd.to_numeric(trades.get("fold", 0), errors="coerce").fillna(0).astype(int).to_numpy())

    baseline_reprice = _baseline_reprice(frame, raw_signal, cost_bps=cost_bps, horizon_sec=horizon_sec, latency_sec=latency_sec, exit_spec=exit_spec)
    baseline_reprice.to_csv(out / "real_fee_v17_reprice.csv", index=False)

    candidate_filters = _candidate_filter_atoms(frame, raw_signal, candidate_quantiles)
    candidate_combos = _candidate_filter_combos(candidate_filters, selected_filters, max_filter_count=max_filter_count)
    candidates = _evaluate_candidates(frame, raw_signal, candidate_combos, cost_bps=cost_bps, horizon_sec=horizon_sec, latency_sec=latency_sec, exit_spec=exit_spec)
    candidates.to_csv(out / "real_fee_filter_family_candidates.csv", index=False)

    stress = _stress_selected(frame, selected_signal, fee_side_values=stress_fee_side_bps_values, latency_values=stress_latency_sec_values, horizon_sec=horizon_sec, exit_spec=exit_spec)
    stress.to_csv(out / "real_fee_latency_fee_stress.csv", index=False)
    stress_summary = _stress_summary(stress, gate)

    miss = _missed_trade_stress(trades, miss_probabilities=[0.1, 0.2, 0.3, 0.4, gate.missed_trade_gate_probability, 0.6], scenarios=random_scenarios, seed=seed)
    miss.to_csv(out / "real_fee_missed_trade_stress.csv", index=False)
    extra = _extra_cost_reserve(trades, extra_cost_bps_values=[0, 1, 2, 3, 5, 7.5, gate.extra_cost_gate_bps])
    extra.to_csv(out / "real_fee_extra_cost_reserve.csv", index=False)

    null_df, family_null = _fee_filter_family_shift_null(
        frame=frame,
        raw_signal=raw_signal,
        selected_filters=selected_filters,
        candidate_combos=candidate_combos,
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
        exit_spec=exit_spec,
        shift_null_runs=shift_null_runs,
        selected_total=float(selected_metrics.get("total_net_pnl_bps", 0.0)),
        selected_mean=float(selected_metrics.get("mean_net_pnl_bps", 0.0)),
        min_trades=gate.min_trades,
    )
    null_df.to_csv(out / "real_fee_filter_family_shift_null.csv", index=False)

    aggregate = _aggregate(
        selected_metrics=selected_metrics,
        folds=folds,
        bootstrap=bootstrap,
        stability=stability,
        path=path,
        stress_summary=stress_summary,
        family_null=family_null,
        miss=miss,
        extra=extra,
        gate=gate,
    )
    result: dict[str, object] = {
        "v17_run_dir": str(run),
        "out_dir": str(out),
        "fee_spec": fee_spec.to_dict(),
        "horizon_sec": float(horizon_sec),
        "latency_sec": float(latency_sec),
        "take_profit_bps": float(take_profit_bps),
        "stop_loss_bps": float(stop_loss_bps),
        "execution_route": "taker_entry_taker_exit_selected_for_v19",
        "selected_filters": [f.to_dict() for f in selected_filters],
        "candidate_quantiles": [float(q) for q in candidate_quantiles],
        "max_filter_count": int(max_filter_count),
        "candidate_count": int(len(candidates)),
        "shift_null_runs": int(len(null_df)),
        "stress_fee_side_bps_values": [float(x) for x in stress_fee_side_bps_values],
        "stress_latency_sec_values": [float(x) for x in stress_latency_sec_values],
        "baseline_reprice": baseline_reprice.to_dict(orient="records"),
        "aggregate": aggregate,
        "gate_config": gate.to_dict(),
    }
    (out / "summary.json").write_text(json.dumps(_jsonable(result), indent=2), encoding="utf-8")
    _write_report(out / "REPORT.md", result, folds, candidates, stress, miss, extra)
    (out / "DONE.marker").write_text("ok\n", encoding="utf-8")
    return _jsonable(result)


def _dedupe_float(values: list[float]) -> list[float]:
    out: list[float] = []
    seen: set[float] = set()
    for x in values:
        v = round(float(x), 12)
        if v not in seen:
            seen.add(v)
            out.append(float(x))
    return out


def _values_for_filter(frame: pd.DataFrame, directions: np.ndarray, spec: FeeGuardFilterSpec) -> np.ndarray:
    if spec.column not in frame.columns:
        return np.full(len(frame), np.nan, dtype=float)
    values = pd.to_numeric(frame[spec.column], errors="coerce").to_numpy(dtype=float)
    transform = str(spec.transform).lower()
    if transform == "raw":
        return values
    if transform == "abs":
        return np.abs(values)
    if transform == "signed":
        return np.asarray(directions, dtype=float) * values
    raise ValueError(f"unknown fee guard transform: {spec.transform}")


def _mask_for_filters(frame: pd.DataFrame, directions: np.ndarray, specs: list[FeeGuardFilterSpec]) -> np.ndarray:
    mask = np.ones(len(frame), dtype=bool)
    for spec in specs:
        values = _values_for_filter(frame, directions, spec)
        if spec.operator == ">=":
            mask &= values >= float(spec.threshold)
        elif spec.operator == "<=":
            mask &= values <= float(spec.threshold)
        else:
            raise ValueError(f"unknown filter operator: {spec.operator}")
        mask &= np.isfinite(values)
    return mask


def _candidate_filter_atoms(frame: pd.DataFrame, raw_signal: np.ndarray, quantiles: list[float]) -> list[FeeGuardFilterSpec]:
    selected = np.asarray(raw_signal, dtype=int) != 0
    atoms: list[FeeGuardFilterSpec] = []
    # Curated V19 fee family.  Keeping this family compact is intentional: it corrects
    # the filters we actually considered for high fees without turning the single sample
    # into an unlimited data-mining exercise.  The selected V19 guard is included.
    family_defs: list[tuple[str, str, list[str], list[float]]] = [
        ("abs", "prob_edge", [">="], [0.2, 0.3, 0.4, 0.5]),
        ("signed", "kline_15s_signal", [">="], [0.1, 0.2, 0.3]),
        ("raw", "kline_15s_rv_12_bps", ["<="], [0.8, 0.9]),
        ("raw", "ofi_sum_l5_norm", [">="], [0.1, 0.2]),
        ("raw", "ofi_sum_l10_norm", [">="], [0.1, 0.2]),
        ("raw", "kline_1m_rv_3_bps", ["<="], [0.6, 0.7, 0.8]),
        ("raw", "kline_1m_range_z_6", [">="], [0.1, 0.2, 0.3]),
        ("raw", "kline_15s_rv_6_bps", [">="], [0.1, 0.2]),
    ]
    selected_frame = frame.loc[selected].reset_index(drop=True)
    selected_dirs = raw_signal[selected]
    for transform, col, ops, qs in family_defs:
        if col not in frame.columns or selected_frame.empty:
            continue
        dummy = FeeGuardFilterSpec(transform, col, ">=", 0.0)
        vals = _values_for_filter(selected_frame, selected_dirs, dummy)
        vals = vals[np.isfinite(vals)]
        if len(vals) == 0:
            continue
        for q in qs:
            # Keep external candidate_quantiles as an optional upper-level allow-list.
            if quantiles and not any(abs(float(q) - float(allowed)) < 1e-12 for allowed in quantiles):
                continue
            threshold = float(np.quantile(vals, float(q)))
            for op in ops:
                atoms.append(FeeGuardFilterSpec(transform, col, op, threshold, float(q)))
    out: list[FeeGuardFilterSpec] = []
    seen: set[tuple[str, str, str, float]] = set()
    for atom in atoms + default_v19_fee_filters():
        if atom.key not in seen:
            seen.add(atom.key)
            out.append(atom)
    return out

def _candidate_filter_combos(atoms: list[FeeGuardFilterSpec], selected: list[FeeGuardFilterSpec], *, max_filter_count: int) -> list[list[FeeGuardFilterSpec]]:
    combos: list[list[FeeGuardFilterSpec]] = []
    seen: set[tuple[tuple[str, str, str, float], ...]] = set()

    def add(combo: tuple[FeeGuardFilterSpec, ...] | list[FeeGuardFilterSpec]) -> None:
        ordered = tuple(sorted((f.key for f in combo)))
        if ordered in seen:
            return
        # Do not allow multiple thresholds on the same transformed column in one combo.
        features = [(f.transform, f.column) for f in combo]
        if len(set(features)) != len(features):
            return
        seen.add(ordered)
        combos.append(list(combo))

    add(tuple(selected))
    for k in range(1, int(max_filter_count) + 1):
        for combo in combinations(atoms, k):
            add(combo)
    return combos


def _evaluate_candidates(frame: pd.DataFrame, raw_signal: np.ndarray, combos: list[list[FeeGuardFilterSpec]], *, cost_bps: float, horizon_sec: float, latency_sec: float, exit_spec: ExitLockSpec) -> pd.DataFrame:
    arrays = execution_path_arrays(frame, horizon_sec=horizon_sec, latency_sec=latency_sec)
    p_long, p_short = _precompute_exit_pnl_by_row(arrays, cost_bps=cost_bps, spec=exit_spec)
    idx = np.flatnonzero(np.asarray(raw_signal, dtype=int) != 0).astype(int)
    dirs = np.asarray(raw_signal, dtype=int)[idx]
    sub_frame = frame.iloc[idx].reset_index(drop=True)
    folds = pd.to_numeric(frame.get("fold", 0), errors="coerce").fillna(0).astype(int).to_numpy()
    rows: list[dict[str, object]] = []
    for combo in combos:
        keep = _mask_for_filters(sub_frame, dirs, combo)
        kept_idx = idx[keep]
        kept_dirs = dirs[keep]
        pnl = np.where(kept_dirs > 0, p_long[kept_idx], p_short[kept_idx]).astype(float) if len(kept_idx) else np.asarray([], dtype=float)
        finite = np.isfinite(pnl)
        pnl = pnl[finite]
        kept_folds = folds[kept_idx][finite] if len(kept_idx) else np.asarray([], dtype=int)
        metrics = _metrics_from_pnl(pnl)
        fdf = _fold_metrics_from_arrays(pnl, kept_folds)
        row = {
            "filter_count": int(len(combo)),
            "filters_json": json.dumps([f.to_dict() for f in combo], sort_keys=True),
            "is_selected_v19": bool(_same_filter_set(combo, default_v19_fee_filters())),
            **metrics,
            "fold_min_total_net_pnl_bps": float(fdf["total_net_pnl_bps"].min()) if not fdf.empty else 0.0,
            "fold_min_mean_net_pnl_bps": float(fdf["mean_net_pnl_bps"].min()) if not fdf.empty else 0.0,
            "folds_with_trades": int((fdf["trades"] > 0).sum()) if not fdf.empty else 0,
        }
        rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(["total_net_pnl_bps", "hit_rate", "mean_net_pnl_bps"], ascending=False).reset_index(drop=True)


def _metrics_from_pnl(pnl: np.ndarray) -> dict[str, float]:
    arr = np.asarray(pnl, dtype=float)
    if len(arr) == 0:
        return {"trades": 0.0, "hit_rate": 0.0, "mean_net_pnl_bps": 0.0, "median_net_pnl_bps": 0.0, "total_net_pnl_bps": 0.0, "max_drawdown_bps": 0.0, "profit_factor": 0.0}
    equity = np.cumsum(arr)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    return {
        "trades": float(len(arr)),
        "hit_rate": float((arr > 0).mean()),
        "mean_net_pnl_bps": float(arr.mean()),
        "median_net_pnl_bps": float(np.median(arr)),
        "total_net_pnl_bps": float(arr.sum()),
        "max_drawdown_bps": float(dd.min()) if len(dd) else 0.0,
        "profit_factor": float(wins.sum() / abs(losses.sum())) if abs(losses.sum()) > 0 else (float("inf") if wins.sum() > 0 else 0.0),
    }


def _fold_metrics_from_arrays(pnl: np.ndarray, folds: np.ndarray) -> pd.DataFrame:
    if len(pnl) == 0:
        return pd.DataFrame(columns=["fold", "trades", "hit_rate", "mean_net_pnl_bps", "total_net_pnl_bps"])
    return _fold_metrics(pd.DataFrame({"fold": folds.astype(int), "net_pnl_bps": pnl.astype(float)}))

def _same_filter_set(a: list[FeeGuardFilterSpec], b: list[FeeGuardFilterSpec]) -> bool:
    return tuple(sorted(f.key for f in a)) == tuple(sorted(f.key for f in b))


def _baseline_reprice(frame: pd.DataFrame, raw_signal: np.ndarray, *, cost_bps: float, horizon_sec: float, latency_sec: float, exit_spec: ExitLockSpec) -> pd.DataFrame:
    tmp = frame.copy()
    tmp["signal"] = raw_signal
    bt, metrics = backtest_fixed_signals_taker_bidask_exit_lock(tmp, cost_bps=cost_bps, horizon_sec=horizon_sec, latency_sec=latency_sec, spec=exit_spec)
    trades = bt.loc[bt["traded"].astype(int) == 1]
    fold = _fold_metrics(trades)
    return pd.DataFrame([{
        "label": "v17_repriced_with_user_taker_fee",
        **_jsonable(metrics),
        "fold_min_total_net_pnl_bps": float(fold["total_net_pnl_bps"].min()) if not fold.empty else 0.0,
        "fold_min_mean_net_pnl_bps": float(fold["mean_net_pnl_bps"].min()) if not fold.empty else 0.0,
    }])


def _fold_metrics(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=["fold", "trades", "hit_rate", "mean_net_pnl_bps", "total_net_pnl_bps"])
    tmp = trades.copy()
    tmp["fold"] = pd.to_numeric(tmp.get("fold", 0), errors="coerce").fillna(0).astype(int)
    tmp["net_pnl_bps"] = pd.to_numeric(tmp.get("net_pnl_bps", 0), errors="coerce").fillna(0.0)
    rows = []
    for fold, g in tmp.groupby("fold"):
        pnl = g["net_pnl_bps"].to_numpy(dtype=float)
        rows.append({
            "fold": int(fold),
            "trades": int(len(pnl)),
            "hit_rate": float((pnl > 0).mean()) if len(pnl) else 0.0,
            "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
            "total_net_pnl_bps": float(pnl.sum()) if len(pnl) else 0.0,
        })
    return pd.DataFrame(rows).sort_values("fold").reset_index(drop=True)


def _stress_selected(frame: pd.DataFrame, selected_signal: np.ndarray, *, fee_side_values: list[float], latency_values: list[float], horizon_sec: float, exit_spec: ExitLockSpec) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for latency in latency_values:
        for fee_side in fee_side_values:
            tmp = frame.copy()
            tmp["signal"] = selected_signal
            bt, metrics = backtest_fixed_signals_taker_bidask_exit_lock(tmp, cost_bps=2.0 * float(fee_side), horizon_sec=horizon_sec, latency_sec=float(latency), spec=exit_spec)
            rows.append({
                "taker_fee_bps_per_side": float(fee_side),
                "roundtrip_fee_bps": float(2.0 * float(fee_side)),
                "latency_sec": float(latency),
                **_jsonable(metrics),
            })
    return pd.DataFrame(rows).sort_values(["latency_sec", "taker_fee_bps_per_side"]).reset_index(drop=True)


def _stress_summary(stress: pd.DataFrame, gate: RealFeeLockGate) -> dict[str, object]:
    if stress.empty:
        return {"cells": 0, "gate_cells": 0, "gate_all_positive": False, "gate_min_mean_net_pnl_bps": 0.0, "gate_min_total_net_pnl_bps": 0.0}
    fee = pd.to_numeric(stress["taker_fee_bps_per_side"], errors="coerce")
    lat = pd.to_numeric(stress["latency_sec"], errors="coerce")
    gate_rows = stress.loc[(fee <= float(gate.max_stress_fee_side_bps)) & (lat <= float(gate.max_stress_latency_sec))]
    mean = pd.to_numeric(gate_rows.get("mean_net_pnl_bps", 0), errors="coerce").fillna(0.0)
    total = pd.to_numeric(gate_rows.get("total_net_pnl_bps", 0), errors="coerce").fillna(0.0)
    all_mean = pd.to_numeric(stress.get("mean_net_pnl_bps", 0), errors="coerce").fillna(0.0)
    all_total = pd.to_numeric(stress.get("total_net_pnl_bps", 0), errors="coerce").fillna(0.0)
    return {
        "cells": int(len(stress)),
        "all_cells_min_mean_net_pnl_bps": float(all_mean.min()) if len(all_mean) else 0.0,
        "all_cells_min_total_net_pnl_bps": float(all_total.min()) if len(all_total) else 0.0,
        "all_cells_positive": bool((all_mean > 0).all() and (all_total > 0).all()) if len(all_mean) else False,
        "gate_cells": int(len(gate_rows)),
        "gate_max_fee_side_bps": float(gate.max_stress_fee_side_bps),
        "gate_max_latency_sec": float(gate.max_stress_latency_sec),
        "gate_min_mean_net_pnl_bps": float(mean.min()) if len(mean) else 0.0,
        "gate_min_total_net_pnl_bps": float(total.min()) if len(total) else 0.0,
        "gate_all_positive": bool((mean > 0).all() and (total > 0).all()) if len(mean) else False,
    }


def _missed_trade_stress(trades: pd.DataFrame, *, miss_probabilities: list[float], scenarios: int, seed: int) -> pd.DataFrame:
    pnl = pd.to_numeric(trades.get("net_pnl_bps", 0), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    rng = np.random.default_rng(int(seed))
    rows: list[dict[str, object]] = []
    for miss in _dedupe_float(miss_probabilities):
        keep = rng.random((int(scenarios), len(pnl))) >= float(miss)
        sums = keep.astype(float) @ pnl
        kept = keep.sum(axis=1).astype(float)
        rows.append(_scenario_row({"miss_probability": float(miss)}, sums, kept))
    return pd.DataFrame(rows)


def _extra_cost_reserve(trades: pd.DataFrame, *, extra_cost_bps_values: list[float]) -> pd.DataFrame:
    pnl = pd.to_numeric(trades.get("net_pnl_bps", 0), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    rows: list[dict[str, object]] = []
    for extra in _dedupe_float([float(x) for x in extra_cost_bps_values]):
        adj = pnl - float(extra)
        rows.append({
            "extra_cost_bps_per_trade": float(extra),
            "trades": int(len(adj)),
            "mean_net_pnl_bps": float(adj.mean()) if len(adj) else 0.0,
            "total_net_pnl_bps": float(adj.sum()) if len(adj) else 0.0,
            "hit_rate": float((adj > 0).mean()) if len(adj) else 0.0,
        })
    return pd.DataFrame(rows)


def _scenario_row(prefix: dict[str, object], sums: np.ndarray, kept: np.ndarray) -> dict[str, object]:
    q = np.percentile(sums, [1, 5, 10, 50]) if len(sums) else [0.0, 0.0, 0.0, 0.0]
    row = dict(prefix)
    row.update({
        "scenarios": int(len(sums)),
        "mean_kept_trades": float(kept.mean()) if len(kept) else 0.0,
        "min_total_bps": float(sums.min()) if len(sums) else 0.0,
        "p01_total_bps": float(q[0]),
        "p05_total_bps": float(q[1]),
        "p10_total_bps": float(q[2]),
        "median_total_bps": float(q[3]),
        "mean_total_bps": float(sums.mean()) if len(sums) else 0.0,
        "positive_scenario_rate": float((sums > 0.0).mean()) if len(sums) else 0.0,
    })
    return row


def _fee_filter_family_shift_null(
    *,
    frame: pd.DataFrame,
    raw_signal: np.ndarray,
    selected_filters: list[FeeGuardFilterSpec],
    candidate_combos: list[list[FeeGuardFilterSpec]],
    cost_bps: float,
    horizon_sec: float,
    latency_sec: float,
    exit_spec: ExitLockSpec,
    shift_null_runs: int,
    selected_total: float,
    selected_mean: float,
    min_trades: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    arrays = execution_path_arrays(frame, horizon_sec=horizon_sec, latency_sec=latency_sec)
    p_long, p_short = _precompute_exit_pnl_by_row(arrays, cost_bps=cost_bps, spec=exit_spec)
    idx = np.flatnonzero(np.asarray(raw_signal, dtype=int) != 0).astype(int)
    sig = np.asarray(raw_signal, dtype=int)[idx]
    n = len(frame)
    min_shift = max(1, int(round(float(horizon_sec) / 0.5)))
    from .slot_veto import _shift_values
    shifts = _shift_values(n=n, shifts=int(shift_null_runs), min_shift=min_shift)

    selected_key = tuple(sorted(f.key for f in selected_filters))
    combo_keys = [tuple(sorted(f.key for f in combo)) for combo in candidate_combos]
    selected_combo_pos = next((i for i, key in enumerate(combo_keys) if key == selected_key), None)
    unique_filters: dict[tuple[str, str, str, float], FeeGuardFilterSpec] = {}
    for combo in candidate_combos:
        for f in combo:
            unique_filters[f.key] = f

    rows: list[dict[str, object]] = []
    exceed_selected = {"total": 0, "mean": 0}
    exceed_family = {"total": 0, "mean": 0}
    exceed_family_constrained = {"total": 0, "mean": 0}
    maxima = {
        "selected_only": {"total": -np.inf, "mean": -np.inf},
        "fee_filter_family": {"total": -np.inf, "mean": -np.inf},
    }

    # Pre-extract numeric columns as numpy arrays to avoid per-candidate pandas overhead.
    col_cache: dict[str, np.ndarray] = {}
    for _key, spec in unique_filters.items():
        if spec.column not in col_cache:
            col_cache[spec.column] = pd.to_numeric(frame[spec.column], errors="coerce").to_numpy(dtype=float) if spec.column in frame.columns else np.full(n, np.nan)

    for shift in shifts:
        rows_idx, dirs = _accepted_shift_positions(idx, sig, int(shift), arrays)
        k = len(rows_idx)
        row: dict[str, object] = {"shift_rows": int(shift), "accepted_shifted_slots": int(k)}
        selected_metrics = {"trades": 0.0, "total_net_pnl_bps": 0.0, "mean_net_pnl_bps": 0.0}
        best_total = -np.inf
        best_mean = -np.inf
        best_total_constrained = -np.inf
        best_mean_constrained = -np.inf
        if k:
            filter_masks: dict[tuple[str, str, str, float], np.ndarray] = {}
            dirs_float = np.asarray(dirs, dtype=float)
            for fkey, spec in unique_filters.items():
                vals = col_cache[spec.column][rows_idx]
                if spec.transform == "abs":
                    vals = np.abs(vals)
                elif spec.transform == "signed":
                    vals = vals * dirs_float
                elif spec.transform == "raw":
                    pass
                else:
                    vals = np.full(k, np.nan)
                if spec.operator == ">=":
                    m = vals >= float(spec.threshold)
                else:
                    m = vals <= float(spec.threshold)
                filter_masks[fkey] = m & np.isfinite(vals)
            pnl_all = np.where(np.asarray(dirs) > 0, p_long[rows_idx], p_short[rows_idx]).astype(float)
            for pos, combo in enumerate(candidate_combos):
                m = np.ones(k, dtype=bool)
                for spec in combo:
                    m &= filter_masks[spec.key]
                    if not m.any():
                        break
                pnl = pnl_all[m]
                pnl = pnl[np.isfinite(pnl)]
                metrics = _metrics_from_pnl(pnl)
                trades = int(metrics.get("trades", 0))
                total = float(metrics.get("total_net_pnl_bps", 0.0))
                mean = float(metrics.get("mean_net_pnl_bps", 0.0))
                if total > best_total:
                    best_total = total
                if mean > best_mean:
                    best_mean = mean
                if trades >= int(min_trades):
                    best_total_constrained = max(best_total_constrained, total)
                    best_mean_constrained = max(best_mean_constrained, mean)
                if selected_combo_pos is not None and pos == selected_combo_pos:
                    selected_metrics = metrics
        for name, total, mean in [
            ("selected_only", float(selected_metrics.get("total_net_pnl_bps", 0.0)), float(selected_metrics.get("mean_net_pnl_bps", 0.0))),
            ("fee_filter_family", best_total if np.isfinite(best_total) else 0.0, best_mean if np.isfinite(best_mean) else 0.0),
        ]:
            maxima[name]["total"] = max(float(maxima[name]["total"]), float(total))
            maxima[name]["mean"] = max(float(maxima[name]["mean"]), float(mean))
            row[f"{name}_max_total_bps"] = float(total)
            row[f"{name}_max_mean_bps"] = float(mean)
        row["fee_filter_family_max_total_bps_constrained"] = float(best_total_constrained) if np.isfinite(best_total_constrained) else 0.0
        row["fee_filter_family_max_mean_bps_constrained"] = float(best_mean_constrained) if np.isfinite(best_mean_constrained) else 0.0
        if float(selected_metrics.get("total_net_pnl_bps", 0.0)) >= selected_total:
            exceed_selected["total"] += 1
        if float(selected_metrics.get("mean_net_pnl_bps", 0.0)) >= selected_mean:
            exceed_selected["mean"] += 1
        if (best_total if np.isfinite(best_total) else 0.0) >= selected_total:
            exceed_family["total"] += 1
        if (best_mean if np.isfinite(best_mean) else 0.0) >= selected_mean:
            exceed_family["mean"] += 1
        if (best_total_constrained if np.isfinite(best_total_constrained) else 0.0) >= selected_total:
            exceed_family_constrained["total"] += 1
        if (best_mean_constrained if np.isfinite(best_mean_constrained) else 0.0) >= selected_mean:
            exceed_family_constrained["mean"] += 1
        rows.append(row)
    df = pd.DataFrame(rows)
    denom = len(df) + 1
    summary = {
        "selected_total_net_pnl_bps": float(selected_total),
        "selected_mean_net_pnl_bps": float(selected_mean),
        "shift_null_runs": int(len(df)),
        "selected_only": {
            "candidate_count": 1,
            "null_total_max_bps": float(maxima["selected_only"]["total"] if np.isfinite(maxima["selected_only"]["total"]) else 0.0),
            "null_mean_max_bps": float(maxima["selected_only"]["mean"] if np.isfinite(maxima["selected_only"]["mean"]) else 0.0),
            "exceed_total_count": int(exceed_selected["total"]),
            "exceed_mean_count": int(exceed_selected["mean"]),
            "addone_p_total_ge_selected": float((exceed_selected["total"] + 1) / denom),
            "addone_p_mean_ge_selected": float((exceed_selected["mean"] + 1) / denom),
        },
        "fee_filter_family": {
            "candidate_count": int(len(candidate_combos)),
            "null_total_max_bps": float(maxima["fee_filter_family"]["total"] if np.isfinite(maxima["fee_filter_family"]["total"]) else 0.0),
            "null_mean_max_bps": float(maxima["fee_filter_family"]["mean"] if np.isfinite(maxima["fee_filter_family"]["mean"]) else 0.0),
            "exceed_total_count": int(exceed_family["total"]),
            "exceed_mean_count": int(exceed_family["mean"]),
            "addone_p_total_ge_selected": float((exceed_family["total"] + 1) / denom),
            "addone_p_mean_ge_selected": float((exceed_family["mean"] + 1) / denom),
            "exceed_total_count_constrained": int(exceed_family_constrained["total"]),
            "exceed_mean_count_constrained": int(exceed_family_constrained["mean"]),
            "addone_p_total_ge_selected_constrained": float((exceed_family_constrained["total"] + 1) / denom),
            "addone_p_mean_ge_selected_constrained": float((exceed_family_constrained["mean"] + 1) / denom),
        },
    }
    return df, summary

def _aggregate(*, selected_metrics, folds, bootstrap, stability, path, stress_summary, family_null, miss, extra, gate: RealFeeLockGate) -> dict[str, object]:
    miss_row = _row_for(miss, "miss_probability", gate.missed_trade_gate_probability)
    extra_row = _row_for(extra, "extra_cost_bps_per_trade", gate.extra_cost_gate_bps)
    agg = {
        "trades": int(selected_metrics.get("trades", 0)),
        "hit_rate": float(selected_metrics.get("hit_rate", 0.0)),
        "mean_net_pnl_bps": float(selected_metrics.get("mean_net_pnl_bps", 0.0)),
        "median_net_pnl_bps": float(selected_metrics.get("median_net_pnl_bps", 0.0)),
        "total_net_pnl_bps": float(selected_metrics.get("total_net_pnl_bps", 0.0)),
        "profit_factor": float(selected_metrics.get("profit_factor", 0.0)),
        "max_drawdown_bps": float(selected_metrics.get("max_drawdown_bps", 0.0)),
        "take_profit_exits": int(selected_metrics.get("take_profit_exits", 0)),
        "horizon_exits": int(selected_metrics.get("horizon_exits", 0)),
        "folds_with_trades": int((folds["trades"].astype(float) > 0).sum()) if not folds.empty else 0,
        "fold_min_mean_net_pnl_bps": float(folds["mean_net_pnl_bps"].min()) if not folds.empty else 0.0,
        "fold_min_total_net_pnl_bps": float(folds["total_net_pnl_bps"].min()) if not folds.empty else 0.0,
        "bootstrap_mean_p05_bps": float(bootstrap.get("mean_p05_bps", 0.0)),
        "bootstrap_total_p05_bps": float(bootstrap.get("total_p05_bps", 0.0)),
        "positive_equal_trade_blocks_5": int(stability.get("positive_equal_trade_blocks_5", 0)),
        "equal_trade_block_5_min_total_bps": float(stability.get("equal_trade_block_5_min_total_bps", 0.0)),
        "top5_winner_removed_total_bps": float(path.get("top5_winner_removed_total_bps", 0.0)),
        "leave_one_trade_out_min_total_bps": float(path.get("leave_one_trade_out_min_total_bps", 0.0)),
        "leave_one_fold_out_min_total_bps": float(path.get("leave_one_fold_out_min_total_bps", 0.0)),
        "stress_gate_min_mean_net_pnl_bps": float(stress_summary.get("gate_min_mean_net_pnl_bps", 0.0)),
        "stress_gate_min_total_net_pnl_bps": float(stress_summary.get("gate_min_total_net_pnl_bps", 0.0)),
        "stress_gate_all_positive": bool(stress_summary.get("gate_all_positive", False)),
        "stress_all_cells_min_total_net_pnl_bps": float(stress_summary.get("all_cells_min_total_net_pnl_bps", 0.0)),
        "missed_trade_gate_p05_total_bps": float(miss_row.get("p05_total_bps", 0.0)),
        "missed_trade_gate_positive_rate": float(miss_row.get("positive_scenario_rate", 0.0)),
        "extra_cost_gate_total_bps": float(extra_row.get("total_net_pnl_bps", 0.0)),
        "selected_only_addone_p_total": float(family_null.get("selected_only", {}).get("addone_p_total_ge_selected", 1.0)),
        "selected_only_addone_p_mean": float(family_null.get("selected_only", {}).get("addone_p_mean_ge_selected", 1.0)),
        "fee_filter_family_addone_p_total": float(family_null.get("fee_filter_family", {}).get("addone_p_total_ge_selected", 1.0)),
        "fee_filter_family_addone_p_mean": float(family_null.get("fee_filter_family", {}).get("addone_p_mean_ge_selected", 1.0)),
        "fee_filter_family_constrained_addone_p_total": float(family_null.get("fee_filter_family", {}).get("addone_p_total_ge_selected_constrained", 1.0)),
        "fee_filter_family_constrained_addone_p_mean": float(family_null.get("fee_filter_family", {}).get("addone_p_mean_ge_selected_constrained", 1.0)),
        "family_null": family_null,
        "stress_summary": stress_summary,
    }
    checks: dict[str, bool] = {}
    checks["enough_trades"] = int(agg["trades"]) >= int(gate.min_trades)
    checks["hit_rate"] = float(agg["hit_rate"]) >= float(gate.min_hit_rate)
    checks["positive_mean"] = float(agg["mean_net_pnl_bps"]) >= float(gate.min_mean_net_pnl_bps)
    checks["positive_total"] = float(agg["total_net_pnl_bps"]) >= float(gate.min_total_net_pnl_bps)
    checks["fold_mean_positive"] = float(agg["fold_min_mean_net_pnl_bps"]) > float(gate.min_fold_mean_net_pnl_bps)
    checks["fold_total_positive"] = float(agg["fold_min_total_net_pnl_bps"]) > float(gate.min_fold_total_net_pnl_bps)
    checks["bootstrap_p05_positive"] = float(agg["bootstrap_mean_p05_bps"]) > float(gate.min_bootstrap_mean_p05_bps)
    checks["selected_shift_null"] = max(float(agg["selected_only_addone_p_total"]), float(agg["selected_only_addone_p_mean"])) <= float(gate.max_family_addone_p)
    checks["fee_family_shift_null"] = max(float(agg["fee_filter_family_constrained_addone_p_total"]), float(agg["fee_filter_family_constrained_addone_p_mean"])) <= float(gate.max_family_addone_p)
    checks["fee_latency_stress"] = bool(agg["stress_gate_all_positive"]) and float(agg["stress_gate_min_mean_net_pnl_bps"]) > float(gate.min_stress_mean_net_pnl_bps) and float(agg["stress_gate_min_total_net_pnl_bps"]) > float(gate.min_stress_total_net_pnl_bps)
    checks["missed_trade_p05_positive"] = float(agg["missed_trade_gate_p05_total_bps"]) > float(gate.missed_trade_min_p05_total_bps)
    checks["extra_cost_positive"] = float(agg["extra_cost_gate_total_bps"]) > float(gate.extra_cost_min_total_bps)
    agg["gate"] = {"passed": bool(all(checks.values())), "checks": checks, "failed_checks": [k for k, v in checks.items() if not v]}
    return _jsonable(agg)


def _row_for(df: pd.DataFrame, column: str, value: float) -> dict[str, object]:
    if df.empty or column not in df.columns:
        return {}
    rows = df.loc[np.isclose(pd.to_numeric(df[column], errors="coerce"), float(value))]
    if rows.empty:
        return {}
    return rows.iloc[0].to_dict()


def _write_report(path: Path, result: dict[str, object], folds: pd.DataFrame, candidates: pd.DataFrame, stress: pd.DataFrame, miss: pd.DataFrame, extra: pd.DataFrame) -> None:
    agg = result["aggregate"]
    fee = result["fee_spec"]
    selected = result["selected_filters"]
    top_candidates = candidates.head(15).to_csv(index=False) if not candidates.empty else "No candidates."
    lines = [
        "# V19 Real-Fee Profit Lock",
        "",
        "V19 uses the user's real fee schedule: 0.0400% taker and 0.0000% maker. 0.0400% equals 4 bps per side, so a taker entry plus taker exit is 8 bps round trip.",
        "",
        "V19 starts from the frozen V17/V18 trading rule, reprices it under the real taker fee, and adds one slot-preserving high-fee guard. The entry/exit rule remains taker/taker because conservative maker-fill simulation did not beat taker/taker on this bundled sample.",
        "",
        "## Fee schedule",
        "",
        "```json",
        json.dumps(_jsonable(fee), indent=2),
        "```",
        "",
        "## Selected high-fee guard",
        "",
        "```json",
        json.dumps(_jsonable(selected), indent=2),
        "```",
        "",
        "## Aggregate gate",
        "",
        "```json",
        json.dumps(_jsonable(agg), indent=2),
        "```",
        "",
        "## Fold metrics",
        "",
        folds.to_csv(index=False).strip() if not folds.empty else "No fold metrics.",
        "",
        "## Top fee-filter family candidates",
        "",
        top_candidates.strip(),
        "",
        "## Fee and latency stress",
        "",
        stress.to_csv(index=False).strip() if not stress.empty else "No stress metrics.",
        "",
        "## Missed-trade stress",
        "",
        miss.to_csv(index=False).strip() if not miss.empty else "No missed-trade metrics.",
        "",
        "## Extra-cost reserve",
        "",
        extra.to_csv(index=False).strip() if not extra.empty else "No extra-cost metrics.",
        "",
        "## Caveat",
        "",
        "V19 is stronger for the user's stated real fee schedule, but it still uses the bundled single sample. Do not call this live stable profit until the frozen V19 rule passes independent multi-day forward validation without retuning thresholds.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
