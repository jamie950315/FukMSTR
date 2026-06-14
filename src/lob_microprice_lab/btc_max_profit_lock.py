from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .btc_contract_data import write_btc_contract_data_plan
from .btc_leverage_lock import BTCSideGuardSpec, _leverage_scenarios, _mask_for_btc_side_guard, default_btc_side_guard
from .exit_lock import ExitLockSpec, backtest_fixed_signals_taker_bidask_exit_lock, execution_path_arrays
from .profit_execution_lock import _accepted_shift_positions, _precompute_exit_pnl_by_row
from .profit_lock import _jsonable, _path_diagnostics
from .profit_success_fast import _stability
from .real_fee_lock import (
    RealFeeLockGate,
    RealFeeSpec,
    _extra_cost_reserve,
    _fold_metrics,
    _mask_for_filters,
    _missed_trade_stress,
    _stress_selected,
    _stress_summary,
    default_v19_fee_filters,
)
from .slot_veto import _shift_values
from .stress import block_bootstrap_pnl


@dataclass(frozen=True)
class BTCMaxProfitRecoverySpec:
    kline_15s_signal_max: float = -0.70
    prob_edge_min: float = 0.50
    kline_1m_range_z_min: float = 0.50
    long_only: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class BTCMaxProfitGate:
    min_trades: int = 11
    min_hit_rate: float = 1.0
    min_total_net_pnl_bps: float = 180.0
    min_mean_net_pnl_bps: float = 16.0
    min_fold_total_net_pnl_bps: float = 0.0
    min_fold_mean_net_pnl_bps: float = 0.0
    min_bootstrap_mean_p05_bps: float = 0.0
    max_full_family_addone_p: float = 0.01
    max_stress_fee_side_bps: float = 10.0
    max_stress_latency_sec: float = 5.0
    missed_trade_gate_probability: float = 0.50
    missed_trade_min_p05_total_bps: float = 0.0
    extra_cost_gate_bps: float = 15.0
    extra_cost_min_total_bps: float = 0.0
    promoted_leverage_cap: float = 5.0
    shock_buffer_bps: float = 1000.0
    maintenance_margin_bps: float = 50.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def default_btc_max_profit_recovery_spec() -> BTCMaxProfitRecoverySpec:
    return BTCMaxProfitRecoverySpec()


def default_btc_max_profit_take_profit_bps() -> float:
    return 50.0


def run_btc_max_profit_lock(
    *,
    v17_run_dir: str | Path,
    out_dir: str | Path,
    fee_spec: RealFeeSpec | None = None,
    side_guard: BTCSideGuardSpec | None = None,
    recovery_spec: BTCMaxProfitRecoverySpec | None = None,
    take_profit_bps: float | None = None,
    stop_loss_bps: float = 0.0,
    horizon_sec: float = 90.0,
    latency_sec: float = 0.5,
    exit_take_profit_candidates: list[float] | None = None,
    stress_fee_side_bps_values: list[float] | None = None,
    stress_latency_sec_values: list[float] | None = None,
    leverage_values: list[float] | None = None,
    shift_null_runs: int = 1000,
    random_scenarios: int = 10000,
    seed: int = 22022,
    gate: BTCMaxProfitGate | None = None,
    write_data_plan: bool = True,
    clean: bool = False,
) -> dict[str, object]:
    run = Path(v17_run_dir)
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    fee_spec = fee_spec or RealFeeSpec(taker_fee_percent=0.0400, maker_fee_percent=0.0000)
    side_guard = side_guard or default_btc_side_guard()
    recovery_spec = recovery_spec or default_btc_max_profit_recovery_spec()
    take_profit_bps = default_btc_max_profit_take_profit_bps() if take_profit_bps is None else float(take_profit_bps)
    exit_take_profit_candidates = _dedupe_float(exit_take_profit_candidates or [0, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60])
    stress_fee_side_bps_values = _dedupe_float(stress_fee_side_bps_values or [4.0, 5.0, 6.0, 7.5, 10.0])
    stress_latency_sec_values = _dedupe_float(stress_latency_sec_values or [0.0, 0.5, 1.0, 2.0, 3.0, 5.0])
    leverage_values = _dedupe_float(leverage_values or [1.0, 2.0, 3.0, 5.0, 10.0, 20.0])
    gate = gate or BTCMaxProfitGate()

    source_path = run / "execution_lock_oof_backtest.csv"
    if not source_path.exists():
        raise FileNotFoundError(f"missing frozen V17 ledger: {source_path}")
    frame = pd.read_csv(source_path)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, format="mixed")
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    raw_signal = pd.to_numeric(frame.get("signal", 0), errors="coerce").fillna(0).astype(int).clip(-1, 1).to_numpy()
    cost_bps = float(fee_spec.taker_taker_roundtrip_bps)

    base_mask = _v20_mask(frame, raw_signal, side_guard)
    recovery_mask = _mask_for_btc_recovery(frame, raw_signal, recovery_spec) & (~base_mask)
    selected_mask = base_mask | recovery_mask
    selected_signal = np.where(selected_mask, raw_signal, 0)
    selected_exit = ExitLockSpec(take_profit_bps=float(take_profit_bps), stop_loss_bps=float(stop_loss_bps), reserve_horizon=True)

    selected_frame = frame.copy()
    selected_frame["signal"] = selected_signal
    selected_bt, selected_metrics = backtest_fixed_signals_taker_bidask_exit_lock(
        selected_frame,
        cost_bps=cost_bps,
        horizon_sec=float(horizon_sec),
        latency_sec=float(latency_sec),
        spec=selected_exit,
    )
    selected_bt["v22_selected"] = selected_signal != 0
    selected_bt["v22_recovery_slot"] = recovery_mask
    selected_bt["real_taker_fee_bps_per_side"] = fee_spec.taker_fee_bps_per_side
    selected_bt["real_maker_fee_bps_per_side"] = fee_spec.maker_fee_bps_per_side
    selected_bt["real_roundtrip_fee_bps"] = selected_bt["traded"].astype(float) * cost_bps
    selected_bt.to_csv(out / "btc_max_profit_oof_backtest.csv", index=False)
    trades = selected_bt.loc[selected_bt["traded"].astype(int) == 1].copy().reset_index(drop=True)
    trades.to_csv(out / "btc_max_profit_trade_ledger.csv", index=False)

    comparison = _comparison_table(
        frame=frame,
        raw_signal=raw_signal,
        side_guard=side_guard,
        recovery_spec=recovery_spec,
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
        stop_loss_bps=stop_loss_bps,
        selected_metrics=selected_metrics,
    )
    comparison.to_csv(out / "btc_v20_v21_v22_comparison.csv", index=False)

    candidates = _evaluate_full_candidates(
        frame=frame,
        raw_signal=raw_signal,
        side_guard=side_guard,
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
        stop_loss_bps=stop_loss_bps,
        exit_take_profit_candidates=exit_take_profit_candidates,
        selected_recovery=recovery_spec,
        selected_take_profit_bps=float(take_profit_bps),
    )
    candidates.to_csv(out / "btc_max_profit_family_candidates.csv", index=False)

    folds = _fold_metrics(trades)
    folds.to_csv(out / "fold_metrics.csv", index=False)
    pnl = pd.to_numeric(trades.get("net_pnl_bps", 0), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    fold_values = pd.to_numeric(trades.get("fold", 0), errors="coerce").fillna(0).astype(int).to_numpy()
    bootstrap = block_bootstrap_pnl(pnl, iterations=5000, block_size=5, seed=seed)
    stability = _stability(selected_bt)
    path = _path_diagnostics(pnl, fold_values)

    stress = _stress_selected(frame, selected_signal, fee_side_values=stress_fee_side_bps_values, latency_values=stress_latency_sec_values, horizon_sec=horizon_sec, exit_spec=selected_exit)
    stress.to_csv(out / "btc_max_profit_fee_latency_stress.csv", index=False)
    stress_summary = _stress_summary(stress, RealFeeLockGate(max_stress_fee_side_bps=gate.max_stress_fee_side_bps, max_stress_latency_sec=gate.max_stress_latency_sec))

    miss = _missed_trade_stress(trades, miss_probabilities=[0.1, 0.2, 0.3, 0.4, gate.missed_trade_gate_probability, 0.6, 0.7], scenarios=random_scenarios, seed=seed)
    miss.to_csv(out / "btc_max_profit_missed_trade_stress.csv", index=False)
    extra = _extra_cost_reserve(trades, extra_cost_bps_values=[0, 1, 2, 3, 5, 7.5, 10, 12, gate.extra_cost_gate_bps])
    extra.to_csv(out / "btc_max_profit_extra_cost_reserve.csv", index=False)

    leverage = _leverage_scenarios(
        trades=trades,
        leverage_values=leverage_values,
        fee_roundtrip_bps=cost_bps,
        maintenance_margin_bps=float(gate.maintenance_margin_bps),
        shock_buffer_bps=float(gate.shock_buffer_bps),
    )
    leverage.to_csv(out / "btc_max_profit_leverage_scenarios.csv", index=False)

    null_df, full_family_null = _full_family_shift_null(
        frame=frame,
        raw_signal=raw_signal,
        side_guard=side_guard,
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
        stop_loss_bps=stop_loss_bps,
        exit_take_profit_candidates=exit_take_profit_candidates,
        selected_total=float(selected_metrics.get("total_net_pnl_bps", 0.0)),
        selected_mean=float(selected_metrics.get("mean_net_pnl_bps", 0.0)),
        shift_null_runs=shift_null_runs,
        min_trades=gate.min_trades,
    )
    null_df.to_csv(out / "btc_max_profit_full_family_shift_null.csv", index=False)

    data_plan = write_btc_contract_data_plan(out_dir=out / "btc_contract_data_plan", start_date="2024-01-01", end_date="2026-06-10", symbol="BTCUSDT") if write_data_plan else {}

    aggregate = _aggregate(
        selected_metrics=selected_metrics,
        comparison=comparison,
        recovery_added=int(recovery_mask.sum()),
        trades=trades,
        folds=folds,
        bootstrap=bootstrap,
        stability=stability,
        path=path,
        stress_summary=stress_summary,
        miss=miss,
        extra=extra,
        leverage=leverage,
        full_family_null=full_family_null,
        gate=gate,
    )

    result: dict[str, object] = {
        "version": "v22_btc_max_profit_lock",
        "v17_run_dir": str(run),
        "out_dir": str(out),
        "fee_spec": fee_spec.to_dict(),
        "horizon_sec": float(horizon_sec),
        "latency_sec": float(latency_sec),
        "take_profit_bps": float(take_profit_bps),
        "stop_loss_bps": float(stop_loss_bps),
        "v19_filters": [f.to_dict() for f in default_v19_fee_filters()],
        "btc_side_guard": side_guard.to_dict(),
        "btc_recovery_spec": recovery_spec.to_dict(),
        "exit_take_profit_candidates": [float(x) for x in exit_take_profit_candidates],
        "recovery_family_candidate_count": int(len(_recovery_candidates())),
        "full_family_candidate_count": int(len(_recovery_candidates()) * len(exit_take_profit_candidates)),
        "stress_fee_side_bps_values": [float(x) for x in stress_fee_side_bps_values],
        "stress_latency_sec_values": [float(x) for x in stress_latency_sec_values],
        "leverage_values": [float(x) for x in leverage_values],
        "shift_null_runs": int(shift_null_runs),
        "data_plan": data_plan,
        "aggregate": aggregate,
        "gate_config": gate.to_dict(),
    }
    (out / "summary.json").write_text(json.dumps(_jsonable(result), indent=2), encoding="utf-8")
    _write_report(out / "REPORT.md", result, comparison, candidates, folds, stress, miss, extra, leverage)
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


def _v20_mask(frame: pd.DataFrame, directions: np.ndarray, side_guard: BTCSideGuardSpec) -> np.ndarray:
    dirs = np.asarray(directions, dtype=int)
    return _mask_for_filters(frame, dirs, default_v19_fee_filters()) & _mask_for_btc_side_guard(frame, dirs, side_guard) & (dirs != 0)


def _mask_for_btc_recovery(frame: pd.DataFrame, directions: np.ndarray, spec: BTCMaxProfitRecoverySpec) -> np.ndarray:
    dirs = np.asarray(directions, dtype=int)
    k = pd.to_numeric(frame.get("kline_15s_signal", np.nan), errors="coerce").to_numpy(dtype=float)
    p = pd.to_numeric(frame.get("prob_edge", np.nan), errors="coerce").to_numpy(dtype=float)
    r = pd.to_numeric(frame.get("kline_1m_range_z_6", np.nan), errors="coerce").to_numpy(dtype=float)
    direction_ok = dirs > 0 if bool(spec.long_only) else dirs != 0
    return direction_ok & np.isfinite(k) & np.isfinite(p) & np.isfinite(r) & (k <= float(spec.kline_15s_signal_max)) & (p >= float(spec.prob_edge_min)) & (r >= float(spec.kline_1m_range_z_min))


def _mask_for_btc_recovery_arrays(dirs: np.ndarray, kline_15s_signal: np.ndarray, prob_edge: np.ndarray, range_z: np.ndarray, spec: BTCMaxProfitRecoverySpec) -> np.ndarray:
    direction_ok = dirs > 0 if bool(spec.long_only) else dirs != 0
    return direction_ok & np.isfinite(kline_15s_signal) & np.isfinite(prob_edge) & np.isfinite(range_z) & (kline_15s_signal <= float(spec.kline_15s_signal_max)) & (prob_edge >= float(spec.prob_edge_min)) & (range_z >= float(spec.kline_1m_range_z_min))


def _recovery_candidates() -> list[BTCMaxProfitRecoverySpec | None]:
    candidates: list[BTCMaxProfitRecoverySpec | None] = [None]
    for k in [-0.4, -0.5, -0.6, -0.7]:
        for p in [0.3, 0.4, 0.5, 0.6]:
            for r in [0.0, 0.25, 0.5, 0.75]:
                candidates.append(BTCMaxProfitRecoverySpec(kline_15s_signal_max=float(k), prob_edge_min=float(p), kline_1m_range_z_min=float(r), long_only=True))
    return candidates


def _comparison_table(*, frame: pd.DataFrame, raw_signal: np.ndarray, side_guard: BTCSideGuardSpec, recovery_spec: BTCMaxProfitRecoverySpec, cost_bps: float, horizon_sec: float, latency_sec: float, stop_loss_bps: float, selected_metrics: dict[str, object]) -> pd.DataFrame:
    base = _v20_mask(frame, raw_signal, side_guard)
    rec = _mask_for_btc_recovery(frame, raw_signal, recovery_spec) & (~base)
    rows: list[dict[str, object]] = []
    specs = [
        ("v20_btc_guard_tp40", np.where(base, raw_signal, 0), 40.0),
        ("v21_btc_guard_tp45", np.where(base, raw_signal, 0), 45.0),
        ("v22_recovery_tp50", np.where(base | rec, raw_signal, 0), 50.0),
    ]
    for label, sig, tp in specs:
        tmp = frame.copy(); tmp["signal"] = sig
        bt, met = backtest_fixed_signals_taker_bidask_exit_lock(tmp, cost_bps=cost_bps, horizon_sec=horizon_sec, latency_sec=latency_sec, spec=ExitLockSpec(take_profit_bps=tp, stop_loss_bps=stop_loss_bps, reserve_horizon=True))
        rows.append({"label": label, **_jsonable(met)})
    rows[-1].update({"selected_v22": True, "selected_total_check": float(selected_metrics.get("total_net_pnl_bps", 0.0))})
    return pd.DataFrame(rows)


def _evaluate_full_candidates(*, frame: pd.DataFrame, raw_signal: np.ndarray, side_guard: BTCSideGuardSpec, cost_bps: float, horizon_sec: float, latency_sec: float, stop_loss_bps: float, exit_take_profit_candidates: list[float], selected_recovery: BTCMaxProfitRecoverySpec, selected_take_profit_bps: float) -> pd.DataFrame:
    base = _v20_mask(frame, raw_signal, side_guard)
    rows: list[dict[str, object]] = []
    for tp in exit_take_profit_candidates:
        exit_spec = ExitLockSpec(take_profit_bps=float(tp), stop_loss_bps=float(stop_loss_bps), reserve_horizon=True)
        for rec in _recovery_candidates():
            m = base.copy()
            if rec is not None:
                m = m | (_mask_for_btc_recovery(frame, raw_signal, rec) & (~base))
            sig = np.where(m, raw_signal, 0)
            tmp = frame.copy(); tmp["signal"] = sig
            bt, metrics = backtest_fixed_signals_taker_bidask_exit_lock(tmp, cost_bps=cost_bps, horizon_sec=horizon_sec, latency_sec=latency_sec, spec=exit_spec)
            trades = bt.loc[bt["traded"].astype(int) == 1].copy()
            fdf = _fold_metrics(trades)
            is_selected = (rec == selected_recovery) and abs(float(tp) - float(selected_take_profit_bps)) < 1e-12
            rows.append({
                "take_profit_bps": float(tp),
                "recovery_json": "null_v20_baseline" if rec is None else json.dumps(rec.to_dict(), sort_keys=True),
                "is_selected_v22": bool(is_selected),
                "recovery_rows_pre_backtest": int(((_mask_for_btc_recovery(frame, raw_signal, rec) & (~base)).sum()) if rec is not None else 0),
                **_jsonable(metrics),
                "fold_min_total_net_pnl_bps": float(fdf["total_net_pnl_bps"].min()) if not fdf.empty else 0.0,
                "fold_min_mean_net_pnl_bps": float(fdf["mean_net_pnl_bps"].min()) if not fdf.empty else 0.0,
            })
    return pd.DataFrame(rows).sort_values(["total_net_pnl_bps", "hit_rate", "mean_net_pnl_bps"], ascending=False).reset_index(drop=True)


def _full_family_shift_null(*, frame: pd.DataFrame, raw_signal: np.ndarray, side_guard: BTCSideGuardSpec, cost_bps: float, horizon_sec: float, latency_sec: float, stop_loss_bps: float, exit_take_profit_candidates: list[float], selected_total: float, selected_mean: float, shift_null_runs: int, min_trades: int) -> tuple[pd.DataFrame, dict[str, object]]:
    arrays = execution_path_arrays(frame, horizon_sec=horizon_sec, latency_sec=latency_sec)
    pnl_by_tp: dict[float, tuple[np.ndarray, np.ndarray]] = {}
    for tp in exit_take_profit_candidates:
        pnl_by_tp[float(tp)] = _precompute_exit_pnl_by_row(arrays, cost_bps=cost_bps, spec=ExitLockSpec(take_profit_bps=float(tp), stop_loss_bps=float(stop_loss_bps), reserve_horizon=True))
    idx = np.flatnonzero(np.asarray(raw_signal, dtype=int) != 0).astype(int)
    sig = np.asarray(raw_signal, dtype=int)[idx]
    min_shift = max(1, int(round(float(horizon_sec) / 0.5)))
    shifts = _shift_values(n=len(frame), shifts=int(shift_null_runs), min_shift=min_shift)
    rec_candidates = _recovery_candidates()
    candidate_count = len(rec_candidates) * len(exit_take_profit_candidates)
    rows: list[dict[str, object]] = []
    exceed_total = 0
    exceed_mean = 0
    null_max_total = -np.inf
    null_max_mean = -np.inf
    for shift in shifts:
        rows_idx, dirs = _accepted_shift_positions(idx, sig, int(shift), arrays)
        best_total = -np.inf
        best_mean = -np.inf
        best_trades = 0
        if len(rows_idx):
            sub = frame.iloc[rows_idx].reset_index(drop=True)
            dirs = np.asarray(dirs, dtype=int)
            base = _v20_mask(sub, dirs, side_guard)
            k = pd.to_numeric(sub.get("kline_15s_signal", np.nan), errors="coerce").to_numpy(dtype=float)
            p = pd.to_numeric(sub.get("prob_edge", np.nan), errors="coerce").to_numpy(dtype=float)
            r = pd.to_numeric(sub.get("kline_1m_range_z_6", np.nan), errors="coerce").to_numpy(dtype=float)
            rec_masks: list[np.ndarray] = []
            for rec in rec_candidates:
                if rec is None:
                    rec_masks.append(np.zeros(len(sub), dtype=bool))
                else:
                    rec_masks.append(_mask_for_btc_recovery_arrays(dirs, k, p, r, rec) & (~base))
            for tp in exit_take_profit_candidates:
                p_long, p_short = pnl_by_tp[float(tp)]
                pnl_all = np.where(dirs > 0, p_long[rows_idx], p_short[rows_idx]).astype(float)
                for rec_m in rec_masks:
                    m = base | rec_m
                    pnl = pnl_all[m]
                    pnl = pnl[np.isfinite(pnl)]
                    if len(pnl) < int(min_trades):
                        continue
                    total = float(pnl.sum())
                    mean = float(pnl.mean()) if len(pnl) else 0.0
                    if total > best_total:
                        best_total = total
                        best_trades = int(len(pnl))
                    if mean > best_mean:
                        best_mean = mean
        best_total = float(best_total if np.isfinite(best_total) else 0.0)
        best_mean = float(best_mean if np.isfinite(best_mean) else 0.0)
        null_max_total = max(null_max_total, best_total)
        null_max_mean = max(null_max_mean, best_mean)
        if best_total >= float(selected_total):
            exceed_total += 1
        if best_mean >= float(selected_mean):
            exceed_mean += 1
        rows.append({
            "shift_rows": int(shift),
            "candidate_count": int(candidate_count),
            "best_constrained_trades": int(best_trades),
            "full_family_max_total_bps_constrained": best_total,
            "full_family_max_mean_bps_constrained": best_mean,
        })
    df = pd.DataFrame(rows)
    denom = len(df) + 1
    summary = {
        "selected_total_net_pnl_bps": float(selected_total),
        "selected_mean_net_pnl_bps": float(selected_mean),
        "shift_null_runs": int(len(df)),
        "candidate_count": int(candidate_count),
        "null_total_max_bps": float(null_max_total if np.isfinite(null_max_total) else 0.0),
        "null_mean_max_bps": float(null_max_mean if np.isfinite(null_max_mean) else 0.0),
        "exceed_total_count": int(exceed_total),
        "exceed_mean_count": int(exceed_mean),
        "addone_p_total_ge_selected": float((exceed_total + 1) / denom),
        "addone_p_mean_ge_selected": float((exceed_mean + 1) / denom),
    }
    return df, summary


def _row_for(df: pd.DataFrame, column: str, value: float) -> dict[str, object]:
    if df.empty or column not in df.columns:
        return {}
    rows = df.loc[np.isclose(pd.to_numeric(df[column], errors="coerce"), float(value))]
    if rows.empty:
        return {}
    return rows.iloc[0].to_dict()


def _aggregate(*, selected_metrics: dict[str, object], comparison: pd.DataFrame, recovery_added: int, trades: pd.DataFrame, folds: pd.DataFrame, bootstrap: dict[str, object], stability: dict[str, object], path: dict[str, object], stress_summary: dict[str, object], miss: pd.DataFrame, extra: pd.DataFrame, leverage: pd.DataFrame, full_family_null: dict[str, object], gate: BTCMaxProfitGate) -> dict[str, object]:
    miss_row = _row_for(miss, "miss_probability", gate.missed_trade_gate_probability)
    extra_row = _row_for(extra, "extra_cost_bps_per_trade", gate.extra_cost_gate_bps)
    lev_rows = leverage.loc[pd.to_numeric(leverage.get("leverage", 0), errors="coerce") <= float(gate.promoted_leverage_cap)] if not leverage.empty else pd.DataFrame()
    v20 = comparison.loc[comparison["label"] == "v20_btc_guard_tp40"].iloc[0].to_dict() if not comparison.empty else {}
    v21 = comparison.loc[comparison["label"] == "v21_btc_guard_tp45"].iloc[0].to_dict() if not comparison.empty else {}
    agg = {
        "baseline_v20_trades": int(v20.get("trades", 0)),
        "baseline_v20_hit_rate": float(v20.get("hit_rate", 0.0)),
        "baseline_v20_total_net_pnl_bps": float(v20.get("total_net_pnl_bps", 0.0)),
        "baseline_v21_tp45_total_net_pnl_bps": float(v21.get("total_net_pnl_bps", 0.0)),
        "recovery_added_slots_pre_backtest": int(recovery_added),
        "trades": int(selected_metrics.get("trades", 0)),
        "hit_rate": float(selected_metrics.get("hit_rate", 0.0)),
        "mean_net_pnl_bps": float(selected_metrics.get("mean_net_pnl_bps", 0.0)),
        "median_net_pnl_bps": float(selected_metrics.get("median_net_pnl_bps", 0.0)),
        "total_net_pnl_bps": float(selected_metrics.get("total_net_pnl_bps", 0.0)),
        "incremental_total_vs_v20_bps": float(selected_metrics.get("total_net_pnl_bps", 0.0)) - float(v20.get("total_net_pnl_bps", 0.0)),
        "incremental_total_vs_v21_tp45_bps": float(selected_metrics.get("total_net_pnl_bps", 0.0)) - float(v21.get("total_net_pnl_bps", 0.0)),
        "profit_factor": float(selected_metrics.get("profit_factor", 0.0)) if np.isfinite(float(selected_metrics.get("profit_factor", 0.0))) else "inf",
        "max_drawdown_bps": float(selected_metrics.get("max_drawdown_bps", 0.0)),
        "take_profit_exits": int(selected_metrics.get("take_profit_exits", 0)),
        "horizon_exits": int(selected_metrics.get("horizon_exits", 0)),
        "folds_with_trades": int((folds["trades"].astype(float) > 0).sum()) if not folds.empty else 0,
        "fold_min_total_net_pnl_bps": float(folds["total_net_pnl_bps"].min()) if not folds.empty else 0.0,
        "fold_min_mean_net_pnl_bps": float(folds["mean_net_pnl_bps"].min()) if not folds.empty else 0.0,
        "bootstrap_mean_p05_bps": float(bootstrap.get("mean_p05_bps", 0.0)),
        "bootstrap_total_p05_bps": float(bootstrap.get("total_p05_bps", 0.0)),
        "positive_equal_trade_blocks_5": int(stability.get("positive_equal_trade_blocks_5", 0)),
        "positive_equal_trade_blocks_10": int(stability.get("positive_equal_trade_blocks_10", 0)),
        "equal_trade_block_5_min_total_bps": float(stability.get("equal_trade_block_5_min_total_bps", 0.0)),
        "equal_trade_block_10_min_total_bps": float(stability.get("equal_trade_block_10_min_total_bps", 0.0)),
        "top5_winner_removed_total_bps": float(path.get("top5_winner_removed_total_bps", 0.0)),
        "top7_winner_removed_total_bps": float(path.get("top7_winner_removed_total_bps", 0.0)),
        "leave_one_trade_out_min_total_bps": float(path.get("leave_one_trade_out_min_total_bps", 0.0)),
        "leave_one_fold_out_min_total_bps": float(path.get("leave_one_fold_out_min_total_bps", 0.0)),
        "stress_gate_min_mean_net_pnl_bps": float(stress_summary.get("gate_min_mean_net_pnl_bps", 0.0)),
        "stress_gate_min_total_net_pnl_bps": float(stress_summary.get("gate_min_total_net_pnl_bps", 0.0)),
        "stress_gate_all_positive": bool(stress_summary.get("gate_all_positive", False)),
        "stress_all_cells_min_total_net_pnl_bps": float(stress_summary.get("all_cells_min_total_net_pnl_bps", 0.0)),
        "stress_all_cells_min_mean_net_pnl_bps": float(stress_summary.get("all_cells_min_mean_net_pnl_bps", 0.0)),
        "stress_all_cells_positive": bool(stress_summary.get("all_cells_positive", False)),
        "missed_trade_gate_p05_total_bps": float(miss_row.get("p05_total_bps", 0.0)),
        "missed_trade_gate_positive_rate": float(miss_row.get("positive_scenario_rate", 0.0)),
        "extra_cost_gate_total_bps": float(extra_row.get("total_net_pnl_bps", 0.0)),
        "full_family_addone_p_total": float(full_family_null.get("addone_p_total_ge_selected", 1.0)),
        "full_family_addone_p_mean": float(full_family_null.get("addone_p_mean_ge_selected", 1.0)),
        "full_family_null": full_family_null,
        "leverage_promoted_cap": float(gate.promoted_leverage_cap),
        "leverage_promoted_rows_all_pass_shock_buffer": bool(lev_rows["passes_shock_buffer"].astype(bool).all()) if not lev_rows.empty else False,
        "stress_summary": stress_summary,
    }
    checks = {
        "enough_trades": int(agg["trades"]) >= int(gate.min_trades),
        "hit_rate": float(agg["hit_rate"]) >= float(gate.min_hit_rate),
        "mean_profit": float(agg["mean_net_pnl_bps"]) >= float(gate.min_mean_net_pnl_bps),
        "total_profit": float(agg["total_net_pnl_bps"]) >= float(gate.min_total_net_pnl_bps),
        "fold_total_positive": float(agg["fold_min_total_net_pnl_bps"]) > float(gate.min_fold_total_net_pnl_bps),
        "fold_mean_positive": float(agg["fold_min_mean_net_pnl_bps"]) > float(gate.min_fold_mean_net_pnl_bps),
        "bootstrap_p05_positive": float(agg["bootstrap_mean_p05_bps"]) > float(gate.min_bootstrap_mean_p05_bps),
        "full_family_null": max(float(agg["full_family_addone_p_total"]), float(agg["full_family_addone_p_mean"])) <= float(gate.max_full_family_addone_p),
        "fee_latency_stress": bool(agg["stress_gate_all_positive"]) and float(agg["stress_gate_min_mean_net_pnl_bps"]) > 0.0 and float(agg["stress_gate_min_total_net_pnl_bps"]) > 0.0,
        "missed_trade_p05_positive": float(agg["missed_trade_gate_p05_total_bps"]) > float(gate.missed_trade_min_p05_total_bps),
        "extra_cost_positive": float(agg["extra_cost_gate_total_bps"]) > float(gate.extra_cost_min_total_bps),
        "promoted_leverage_buffer": bool(agg["leverage_promoted_rows_all_pass_shock_buffer"]),
    }
    agg["gate"] = {"passed": bool(all(checks.values())), "checks": checks, "failed_checks": [k for k, v in checks.items() if not v]}
    return _jsonable(agg)


def _write_report(path: Path, result: dict[str, object], comparison: pd.DataFrame, candidates: pd.DataFrame, folds: pd.DataFrame, stress: pd.DataFrame, miss: pd.DataFrame, extra: pd.DataFrame, leverage: pd.DataFrame) -> None:
    agg = result["aggregate"]
    lines = [
        "# V22 BTC Max-Profit Lock",
        "",
        "V22 starts from the V20/V21 BTC contract work. It combines the V20 BTC entry rule, a tiny long-only recovery sleeve, and a 50 bps slot-preserving take-profit target. The selected rule is corrected against the full recovery-plus-exit family.",
        "",
        "## Frozen inputs",
        "",
        "```json",
        json.dumps({
            "fee_spec": result["fee_spec"],
            "horizon_sec": result["horizon_sec"],
            "latency_sec": result["latency_sec"],
            "take_profit_bps": result["take_profit_bps"],
            "stop_loss_bps": result["stop_loss_bps"],
            "v19_filters": result["v19_filters"],
            "btc_side_guard": result["btc_side_guard"],
            "btc_recovery_spec": result["btc_recovery_spec"],
        }, indent=2),
        "```",
        "",
        "## Aggregate gate",
        "",
        "```json",
        json.dumps(_jsonable(agg), indent=2),
        "```",
        "",
        "## V20/V21/V22 comparison",
        "",
        comparison.to_csv(index=False).strip(),
        "",
        "## Top full-family candidates",
        "",
        candidates.head(20).to_csv(index=False).strip() if not candidates.empty else "No candidates.",
        "",
        "## Fold metrics",
        "",
        folds.to_csv(index=False).strip() if not folds.empty else "No folds.",
        "",
        "## Fee and latency stress",
        "",
        stress.to_csv(index=False).strip(),
        "",
        "## Missed-trade stress",
        "",
        miss.to_csv(index=False).strip(),
        "",
        "## Extra-cost reserve",
        "",
        extra.to_csv(index=False).strip(),
        "",
        "## Leverage scenarios",
        "",
        leverage.to_csv(index=False).strip(),
        "",
        "## Caveat",
        "",
        "This remains a bundled-sample research result. The V22 rule should now be frozen before independent BTC contract days are used. The leverage rows are simplified account-return scenarios, not exchange liquidation guarantees.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
